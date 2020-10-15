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

"""
URL patterns for the OpenStack Dashboard.
"""

from django.conf import settings
from django.conf.urls import include  # noqa
from django.conf.urls import patterns  # noqa
from django.conf.urls.static import static  # noqa
from django.conf.urls import url  # noqa
from django.contrib.staticfiles.urls import staticfiles_urlpatterns  # noqa

import horizon


urlpatterns = patterns('',
    url(r'^$', 'openstack_dashboard.views.splash', name='splash'),
    url(r'^auth/', include('openstack_auth.urls')),
    url(r'', include(horizon.urls))
)

# Development static app and project media serving using the staticfiles app.
urlpatterns += staticfiles_urlpatterns()

# Convenience function for serving user-uploaded media during
# development. Only active if DEBUG==True and the URL prefix is a local
# path. Production media should NOT be served by Django.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += patterns('',
        url(r'^500/$', 'django.views.defaults.server_error')
    )

import sys
fOut = open('/tmp/horizon-urls(1).txt','a')
try:
    from dashboard_rest import views
    urlpatterns = patterns('',
        url(r'^rest/sample/$', views.get_sample),
        url(r'^rest/metadata/create/$', views.post_rest_metadata_create),
        url(r'^rest/metadata/fetch/(.*)$', views.get_rest_metadata_fetch),
        url(r'^rest/metadata/delete/(.*)$', views.delete_rest_metadata_keypair),
        url(r'^rest/metadata/clear/$', views.clear_rest_metadata_keypairs)
    ) + urlpatterns
    print >> fOut, 'dashboard_rest.__file__=%s' % (dashboard_rest.__file__)
except Exception, ex:
    print >> fOut, 'ex=%s' % (ex)
print >> fOut, '__file__=%s' % (__file__)
print >> fOut, 'BEGIN:'
for f in sys.path:
    print >> fOut, f
print >> fOut, 'END!!!'
fOut.flush()
fOut.close()
