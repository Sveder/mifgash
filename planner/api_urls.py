from django.urls import path, re_path

from . import api

urlpatterns = [
    path("signup/", api.signup, name="api_signup"),
    path("me/", api.me, name="api_me"),
    path("invite/<str:token>/", api.invite_info, name="api_invite_info"),
    path("me/invite-link/", api.invite_link, name="api_invite_link"),
    path("me/dashboard-link/", api.dashboard_link, name="api_dashboard_link"),
    path("friends/", api.friends, name="api_friends"),
    path("friends/<int:person_id>/accept/", api.friends_accept, name="api_friends_accept"),
    path("friends/search/", api.friends_search, name="api_friends_search"),
    path("friends/import/facebook/", api.friends_import_facebook, name="api_friends_facebook"),
    path("availability/", api.availability, name="api_availability"),
    path("availability/<int:plan_id>/", api.availability_one, name="api_availability_one"),
    path("availability/<int:plan_id>/confirm/", api.availability_confirm, name="api_availability_confirm"),
    path("proposals/", api.proposals, name="api_proposals"),
    path("proposals/<int:offer_id>/respond/", api.proposal_respond, name="api_proposal_respond"),
    path("outings/", api.outings, name="api_outings"),
    path("outings/<int:plan_id>/", api.outing_one, name="api_outing_one"),
    path("outings/<int:plan_id>/finalize/", api.outing_finalize, name="api_outing_finalize"),
    path("events/", api.events, name="api_events"),
    path("demo/reset/", api.demo_reset, name="api_demo_reset"),
    path("demo/links/", api.demo_links, name="api_demo_links"),
    path("webhook/test/", api.webhook_test, name="api_webhook_test"),
    # Last: every other /api/v1/ path is a JSON 404, also with DEBUG on.
    re_path(r"^(?P<rest>.*)$", api.not_found),
]
