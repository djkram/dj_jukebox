from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.internal.userkit import user_email, user_username


class AccountAdapter(DefaultAccountAdapter):
    def populate_username(self, request, user):
        # Set username = email as initial value; CustomSignupForm.signup() will
        # overwrite it with full_name once the user record exists.
        email = user_email(user)
        if email:
            user_username(user, email)
        else:
            super().populate_username(request, user)
