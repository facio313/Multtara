from django.contrib import admin
from .models import User, UserActivity, Passport

admin.site.register(User)
admin.site.register(UserActivity)
admin.site.register(Passport)
