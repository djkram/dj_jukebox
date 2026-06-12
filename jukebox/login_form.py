from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _


class CustomLoginForm:
    """
    Registered via ACCOUNT_FORMS = {'login': 'jukebox.login_form.CustomLoginForm'}.

    Dynamically subclasses allauth's LoginForm at instantiation time to avoid the
    circular import that occurs if we subclass it at module level (allauth imports
    ACCOUNT_SIGNUP_FORM_CLASS from jukebox.forms while loading allauth.account.forms,
    and jukebox.forms would be importing from allauth.account.forms simultaneously).

    Adds specific error messages when auth fails because:
      - User registered via Google/Spotify (no usable password set)
      - User email hasn't been verified yet
    """

    def __new__(cls, *args, **kwargs):
        from allauth.account.forms import LoginForm as AllauthLoginForm

        class _Form(AllauthLoginForm):
            def _clean_with_password(self, credentials):
                from allauth.account.adapter import get_adapter
                from allauth.account.internal import flows
                from allauth.account.internal.flows.login import Login
                from allauth.core import context
                from allauth.account.models import EmailAddress
                from allauth.socialaccount.models import SocialAccount

                adapter = get_adapter(self.request)
                user = adapter.authenticate(self.request, **credentials)
                if user:
                    login = Login(user=user, email=credentials.get("email"))
                    if flows.login.is_login_rate_limited(context.request, login):
                        raise adapter.validation_error("too_many_login_attempts")
                    self._login = login
                    self.user = user
                else:
                    email = credentials.get("email", "")
                    User = get_user_model()
                    try:
                        target = User.objects.get(email__iexact=email)
                        if not target.has_usable_password():
                            providers = list(
                                SocialAccount.objects.filter(user=target)
                                .values_list("provider", flat=True)
                            )
                            if providers:
                                _names = {"google": "Google", "spotify": "Spotify"}
                                name = _names.get(providers[0], providers[0].capitalize())
                                raise forms.ValidationError(
                                    _(
                                        "Has creat el teu compte amb %(name)s. "
                                        "Utilitza el botó de %(name)s per entrar, o "
                                        "restableix la contrasenya si vols fer servir l'email."
                                    )
                                    % {"name": name}
                                )
                        else:
                            ea = EmailAddress.objects.filter(
                                user=target, email__iexact=email
                            ).first()
                            if ea and not ea.verified:
                                raise forms.ValidationError(
                                    _(
                                        "El correu %(email)s encara no ha estat verificat. "
                                        "Revisa la safata d'entrada i fes clic a l'enllaç de confirmació."
                                    )
                                    % {"email": email}
                                )
                    except User.DoesNotExist:
                        pass
                    login_method = flows.login.derive_login_method(
                        self.cleaned_data["login"]
                    )
                    raise adapter.validation_error(
                        f"{login_method.value}_password_mismatch"
                    )
                return self.cleaned_data

        return _Form(*args, **kwargs)
