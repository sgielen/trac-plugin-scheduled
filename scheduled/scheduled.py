import re
import time

from trac.core import *
from trac.web.chrome import INavigationContributor, ITemplateProvider, add_stylesheet, Chrome
from trac.web.main import IRequestHandler
from trac.web.api import *
from trac.env import IEnvironmentSetupParticipant
from trac.util.translation import _
from genshi.builder import tag
from pkg_resources import resource_filename

class Scheduled(Component):
	database_version = 1

	implements(INavigationContributor, IRequestHandler, ITemplateProvider, IEnvironmentSetupParticipant)

	@property
	def current_database_version(self):
		for row in self.env.db_query("SELECT value FROM system WHERE name='scheduled_db_version'"):
			return int(row[0])
		return None

	# INavigationContributor: Add the "scheduled" button to the navigation bar
	def get_active_navigation_item(self, req):
		return 'scheduled'

	def get_navigation_items(self, req):
		yield ('mainnav', 'scheduled', tag.a(_('Scheduled tickets'), href=req.href.scheduled()))

	# IRequestHandler: Show a page upon clicking the navigation "scheduled" button
	def match_request(self, req):
		return re.match(r'/scheduled(?:/.+)?$', req.path_info)
	
	def row_to_dict(self, row):
		return {
			'id': int(row[0]),
			'summary': row[1],
			'description': row[2],
			'recurring_days': int(row[3]),
			'scheduled_start': long(row[4]),
		}
	
	def process_request(self, req):
		add_stylesheet(req, 'scheduled/css/scheduled.css')
		if re.match(r'/scheduled/?$', req.path_info):
			tickets = []
			index = 0
			for row in self.env.db_query("SELECT id, summary, description, recurring_days, scheduled_start FROM scheduled"):
				ticket = self.row_to_dict(row)
				ticket['__idx__'] = index
				tickets.append(ticket)
				index += 1
			return 'scheduled.html', {'scheduled_tickets': tickets}, None
		m = re.match(r'/scheduled/(?:create/?|alter/(\d+)/?)$', req.path_info)
		if m:
			message = None
			ticket = None
			tid = m.group(1)

			if tid is None:
				ticket = {}
			else:
				for row in self.env.db_query("SELECT id, summary, description, recurring_days, scheduled_start FROM scheduled WHERE id=%s", str(tid)):
					ticket = self.row_to_dict(row)
					# microsecond UNIX timestamp to number of days from now
					ticket['scheduled_start'] = ((ticket['scheduled_start'] / 1000000) - time.time()) / (24*3600)
				if ticket is None:
					raise TracError("The given ticket ID was not found.")

			assert ticket is not None, "ticket should be initialised by now"
			
        		if req.method == 'POST':
				try:
					# Save new fields into ticket here, so an exception will not cause
					# the fields to blank
					if 'ticket_id' in req.args:
						ticket['id'] = req.args['ticket_id']
					ticket['summary'] = req.args['field_summary']
					ticket['description'] = req.args['field_description']
					ticket['recurring_days'] = req.args['field_repeatdays']
					ticket['scheduled_start'] = req.args['field_nextdue']
					
					recurring = int(ticket['recurring_days'])
					if recurring < 0:
						raise Exception('Recurring days must not be negative')
					nextdue = float(ticket['scheduled_start'])
					if nextdue <= 0:
						raise Exception('Next due days must be > 0')
					
					ticket['recurring_days'] = recurring
					ticket['scheduled_start'] = (time.time() + nextdue * 3600 * 24) * 1000000
					
					with self.env.db_transaction as db:
						cursor = db.cursor()
						if 'id' in ticket:
							cursor.execute("""
							    UPDATE scheduled SET summary=%s, description=%s, recurring_days=%s,
							    scheduled_start=%s WHERE id=%s""",
							    (ticket['summary'], ticket['description'],
							    ticket['recurring_days'], ticket['scheduled_start'],
							    ticket['id']))
						else:
							cursor.execute("""
							    INSERT INTO scheduled (summary, description, recurring_days,
							    scheduled_start) VALUES (%s, %s, %s, %s)""",
							    (ticket['summary'], ticket['description'],
							    ticket['recurring_days'], ticket['scheduled_start']))
							ticket['id'] = db.get_last_id(cursor, 'scheduled')
						self.log.warning("Saved into schedule, id=%s", str(ticket['id']))
					req.redirect(req.href('/scheduled'))
				except RequestDone, e:
					raise
				except Exception, e:
					message = str(e)
			
			add_stylesheet(req, 'common/css/ticket.css')
			Chrome(self.env).add_wiki_toolbars(req)
			return 'scheduled_create.html', {'message': message, 'ticket': ticket}, None
		else:
			raise HTTPNotFound('Scheduler plugin couldn\'t handle request to %s',
			    req.path_info)
	
	# ITemplateProvider: Provide templates for the pages used in process_request
	def get_templates_dirs(self):
		return [resource_filename(__name__, 'templates')]
	def get_htdocs_dirs(self):
		return [('scheduled', resource_filename(__name__, 'htdocs'))]

	# IEnvironmentSetupParticipant: Create the expected table of scheduled tickets for each version
	def environment_created(self):
		self.upgrade_environment(None)

	def environment_needs_upgrade(self, db):
		# If the database version is too high, say True here;
		# we can't throw exceptions here but we can in upgrade_environment
		return self.current_database_version != self.database_version

	def upgrade_environment(self, db):
		ver=self.current_database_version
		last_supported_database_version=0
		
		if ver > self.database_version:
			raise TracError("""
				Scheduled tickets database version is higher than
				installed plugin supports (database has version %d,
				plugin supports version %d)
				""" % (ver, self.database_version))

		# Sanity checking
		if ver != 0 & ver < last_supported_database_version:
			# TODO: have an option for dropping the complete database
			raise TracError("""
				Scheduled tickets database version is unupgradable (last supported upgrade
				version is %d, current version is %d, last version is %d). Remove the
				'scheduled' table and set scheduled_db_version to 0 in table 'system' to
				work around this missing feature.
				""" % (last_supported_database_version, ver, self.database_version))
		
		self.log.info("Upgrading scheduled ticket table version %d to version %d" % (ver, self.database_version))
		with self.env.db_transaction as db:
			# First, save our old database
			if ver is not None:
				db("CREATE TEMPORARY TABLE scheduled_old AS SELECT * FROM scheduled;")
				db("DROP TABLE scheduled")
			
			# Create our new database
			db("""CREATE TABLE scheduled (
				id integer PRIMARY KEY,
				summary text,
				description text,
				recurring_days integer,
				scheduled_start integer
			)""")

			# Restore our old database
			if ver is not None:
				db("""INSERT INTO scheduled(id, summary, description, recurring_days, scheduled_start)
					SELECT id,summary,description,recurring_days,scheduled_start FROM scheduled_old""")
			
			# Update our version number
			if ver is not None:
				db("UPDATE system SET value=%s WHERE name='scheduled_db_version'", str(self.database_version))
			else:
				db("INSERT INTO system (name, value) VALUES ('scheduled_db_version', %s)", str(self.database_version))

