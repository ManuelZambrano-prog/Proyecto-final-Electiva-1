from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


class RestartSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_token = getattr(settings, 'APP_START_TOKEN', None)
            saved_token = request.session.get('app_start_token')

            if current_token and saved_token != current_token:
                logout(request)
                request.session.flush()
                return redirect('login')

            if current_token and not saved_token:
                request.session['app_start_token'] = current_token

        return self.get_response(request)
