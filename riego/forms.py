from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import HorarioDisponible, PerfilUsuario, SolicitudPlanta


class RegistroForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = get_user_model()
        fields = ('username', 'email', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class UsuarioAdminForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    nombre = forms.CharField(max_length=120, required=True)
    cedula = forms.CharField(max_length=20, required=True)

    class Meta:
        model = get_user_model()
        fields = ('username', 'email', 'nombre', 'cedula')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.set_password(self.cleaned_data['cedula'])
        user.is_staff = False
        user.is_superuser = False

        if commit:
            user.save()
            PerfilUsuario.objects.update_or_create(
                user=user,
                defaults={
                    'nombre': self.cleaned_data['nombre'],
                    'cedula': self.cleaned_data['cedula'],
                },
            )
        return user


class HorarioDisponibleForm(forms.ModelForm):
    fecha = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    hora = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))

    class Meta:
        model = HorarioDisponible
        fields = ('fecha', 'hora', 'disponible')


class NuevaPlantaForm(forms.ModelForm):
    fecha_cita = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='Fecha disponible')
    hora_cita = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}), label='Hora disponible')

    class Meta:
        model = SolicitudPlanta
        fields = ('especie', 'apodo', 'fecha_cita', 'hora_cita')

    def clean(self):
        cleaned_data = super().clean()
        fecha = cleaned_data.get('fecha_cita')
        hora = cleaned_data.get('hora_cita')

        if fecha and hora:
            existe_disponible = HorarioDisponible.objects.filter(
                fecha=fecha,
                hora=hora,
                disponible=True,
            ).exists()
            if not existe_disponible:
                raise forms.ValidationError('La fecha y hora seleccionadas no están disponibles para agendar la instalación.')

        return cleaned_data
