import re

from trac.core import *
from trac.web.chrome import INavigationContributor, ITemplateProvider
from trac.web.main import IRequestHandler
from trac.util.translation import _
from genshi.builder import tag
from pkg_resources import resource_filename

class Scheduled(Component):
	implements(INavigationContributor, IRequestHandler, ITemplateProvider)

	# INavigationContributor: Add the "scheduled" button to the navigation bar
	def get_active_navigation_item(self, req):
		return 'scheduled'

	def get_navigation_items(self, req):
		yield ('mainnav', 'scheduled', tag.a(_('Scheduled tickets'), href=req.href.scheduled()))

	# IRequestHandler: Show a page upon clicking the navigation "scheduled" button
	def match_request(self, req):
		return re.match(r'/scheduled(?:/.+)?$', req.path_info)

	def process_request(self, req):
		return 'scheduled.html', [], None

	# ITemplateProvider: Provide templates for the pages used in process_request
	def get_templates_dirs(self):
		return [resource_filename(__name__, 'templates')]
	def get_htdocs_dirs(self):
		return []
