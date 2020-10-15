# Copyright 2012 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2012 Nebula, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import tables
from horizon.utils import memoized
from horizon import workflows

import requests

from openstack_dashboard import api
from openstack_dashboard.api import keystone
from openstack_dashboard import usage
from openstack_dashboard.usage import quotas

from openstack_dashboard.dashboards.admin.projects \
     import tables as project_tables
from openstack_dashboard.dashboards.admin.projects \
     import workflows as project_workflows
from openstack_dashboard.dashboards.project.overview \
     import views as project_views

PROJECT_INFO_FIELDS = ("domain_id",
                       "domain_name",
                       "name",
                       "description",
                       "enabled")

INDEX_URL = "horizon:admin:projects:index"


class TenantContextMixin(object):
    @memoized.memoized_method
    def get_object(self):
        tenant_id = self.kwargs['tenant_id']
        try:
            return api.keystone.tenant_get(self.request, tenant_id, admin=True)
        except Exception:
            exceptions.handle(self.request,
                              _('Unable to retrieve project information.'),
                              redirect=reverse(INDEX_URL))

    def get_context_data(self, **kwargs):
        context = super(TenantContextMixin, self).get_context_data(**kwargs)
        context['tenant'] = self.get_object()
        return context


class IndexView(tables.DataTableView):
    table_class = project_tables.TenantsTable
    template_name = 'admin/projects/index.html'

    def has_more_data(self, table):
        return self._more

    def get_data(self):
        tenants = []
        marker = self.request.GET.get(
            project_tables.TenantsTable._meta.pagination_param, None)
        domain_context = self.request.session.get('domain_context', None)
        try:
            tenants, self._more = api.keystone.tenant_list(
                self.request,
                domain=domain_context,
                paginate=True,
                marker=marker)
        except Exception:
            self._more = False
            exceptions.handle(self.request,
                              _("Unable to retrieve project list."))
        return tenants


class ProjectUsageView(usage.UsageView):
    table_class = usage.ProjectUsageTable
    usage_class = usage.ProjectUsage
    template_name = 'admin/projects/usage.html'
    csv_response_class = project_views.ProjectUsageCsvRenderer
    csv_template_name = 'project/overview/usage.csv'

    def get_data(self):
        super(ProjectUsageView, self).get_data()
        return self.usage.get_instances()


class CreateProjectView(workflows.WorkflowView):
    workflow_class = project_workflows.CreateProject

    def get_initial(self):
        initial = super(CreateProjectView, self).get_initial()

        # Set the domain of the project
        domain = api.keystone.get_default_domain(self.request)
        initial["domain_id"] = domain.id
        initial["domain_name"] = domain.name

        # get initial quota defaults
        try:
            quota_defaults = quotas.get_default_quota_data(self.request)

            try:
                if api.base.is_service_enabled(self.request, 'network') and \
                   api.neutron.is_quotas_extension_supported(
                       self.request):
                    # TODO(jpichon): There is no API to access the Neutron
                    # default quotas (LP#1204956). For now, use the values
                    # from the current project.
                    project_id = self.request.user.project_id
                    quota_defaults += api.neutron.tenant_quota_get(
                        self.request,
                        tenant_id=project_id)
            except Exception:
                error_msg = _('Unable to retrieve default Neutron quota '
                              'values.')
                self.add_error_to_step(error_msg, 'update_quotas')

            for field in quotas.QUOTA_FIELDS:
                initial[field] = quota_defaults.get(field).limit

        except Exception:
            error_msg = _('Unable to retrieve default quota values.')
            self.add_error_to_step(error_msg, 'update_quotas')

        if (0):
            ##########################################
            import json
            import uuid
            __json__ = json.dumps(initial)
            tmpFname = '/tmp/horizon-CreateProjectView-initial_%s.json' % (uuid.uuid4())
            fOut = open(tmpFname,mode='w')
            print >> fOut, __json__
            fOut.flush()
            fOut.close()
            ##########################################

        return initial


class UpdateProjectView(workflows.WorkflowView):
    workflow_class = project_workflows.UpdateProject

    def get_initial(self):
        initial = super(UpdateProjectView, self).get_initial()

        project_id = self.kwargs['tenant_id']
        initial['project_id'] = project_id

        try:
            # get initial project info
            project_info = api.keystone.tenant_get(self.request, project_id,
                                                   admin=True)
            for field in PROJECT_INFO_FIELDS:
                initial[field] = getattr(project_info, field, None)

            # Retrieve the domain name where the project belong
            if keystone.VERSIONS.active >= 3:
                try:
                    domain = api.keystone.domain_get(self.request,
                                                     initial["domain_id"])
                    initial["domain_name"] = domain.name
                except Exception:
                    exceptions.handle(self.request,
                                      _('Unable to retrieve project domain.'),
                                      redirect=reverse(INDEX_URL))

            # get initial project quota
            quota_data = quotas.get_tenant_quota_data(self.request,
                                                      tenant_id=project_id)
            if api.base.is_service_enabled(self.request, 'network') and \
               api.neutron.is_quotas_extension_supported(self.request):
                quota_data += api.neutron.tenant_quota_get(self.request,
                                                           tenant_id=project_id)
            for field in quotas.QUOTA_FIELDS:
                initial[field] = quota_data.get(field).limit
        except Exception:
            exceptions.handle(self.request,
                              _('Unable to retrieve project details.'),
                              redirect=reverse(INDEX_URL))

        try:
            import os
            import json
            import ConfigParser
            __cwd__ = os.path.abspath(os.curdir)
            __conf__ = os.sep.join([__cwd__,'horizon-database-config.conf'])
            __has__ = False
            __password__ = None
            __keystone_url__ = None
            if (os.path.exists(__conf__)):
                __has__ = True
                __section__ = 'horizon-database-config'
                config = ConfigParser.RawConfigParser()
                config.read(__conf__)
                __password__ = config.get(__section__, 'password')
                __keystone_url__ = config.get(__section__, 'keystone_url')

            if (__keystone_url__) and (__password__):
                __url__ = "%s/tenants/%s/metadata" % (__keystone_url__,project_id)
                headers = {'content-type': 'application/json', 'x-auth-token':__password__}
                r = requests.get(__url__, headers=headers)
                try:
                    __metadata__ = r.json() #json.loads(r.json())
                except:
                    print 'r.json()=%s' % (r.json())
                    __metadata__ = {}
                __m__ = __metadata__.get('metadata',{})
                initial['managed_type'] = __m__.get('managed_type','')
                initial['vpmo_id'] = __m__.get('vpmo_id','')
                initial['mots_id'] = __m__.get('mots_id','')
                initial['uam_role'] = __m__.get('uam_role','')
                initial['global_group'] = __m__.get('global_group','')
                initial['global_group_request_id'] = __m__.get('global_group_request_id','')
                initial['swm_attuid'] = __m__.get('swm_attuid','')
                initial['swm_management_group'] = __m__.get('swm_management_group','')
                for i in xrange(1,50):
                    kname = 'keyname%s' % (i)
                    vname = 'value%s' % (i)
                    if (__m__.has_key(kname)):
                        initial[kname] = __m__[kname]
                    if (__m__.has_key(vname)):
                        initial[vname] = __m__[vname]

                if (1):
                    ##########################################
                    import json
                    import uuid
                    __json__ = json.dumps(__metadata__)
                    tmpFname = '/tmp/horizon-UpdateProjectView-views-1_%s.json' % (uuid.uuid4())
                    fOut = open(tmpFname,mode='w')
                    print >> fOut, '__url__=%s\n' % (__url__)
                    print >> fOut, '__metadata__=%s\n' % (__metadata__)
                    print >> fOut, '__keystone_url__=%s\n' % (__keystone_url__)
                    print >> fOut, 'project_id=%s' % (project_id)
                    print >> fOut, '__password__=%s\n' % (__password__)
                    print >> fOut, 'r.status_code=%s\n' % (r.status_code)
                    print >> fOut, '__json__=%s\n' % (__json__)
                    fOut.flush()
                    fOut.close()
                    ##########################################
        except Exception:
            exceptions.handle(self.request,
                              _('Unable to retrieve project predefined metadata.'),
                              redirect=reverse(INDEX_URL))
        if (0):
            ##########################################
            import json
            import uuid
            __json__ = json.dumps(initial)
            tmpFname = '/tmp/horizon-UpdateProjectView-initial_%s.json' % (uuid.uuid4())
            fOut = open(tmpFname,mode='w')
            print >> fOut, 'cwd=%s\n' % (__cwd__)
            print >> fOut, '__conf__=%s\n' % (__conf__)
            print >> fOut, 'has "%s"=%s\n' % (__conf__,__has__)
            print >> fOut, '__endpoint__=%s\n' % (__endpoint__)
            print >> fOut, 'project_id=%s' % (project_id)
            print >> fOut, __json__
            fOut.flush()
            fOut.close()
            ##########################################

        return initial
