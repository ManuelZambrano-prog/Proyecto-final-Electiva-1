from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Especie, HorarioDisponible, PerfilUsuario, Planta, SolicitudPlanta


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
            PerfilUsuario.objects.get_or_create(
                user=user,
                defaults={'nombre': user.username, 'cedula': ''},
            )
        return user


class UsuarioAdminForm(forms.ModelForm):
    email = forms.EmailField(required=True)
    nombre = forms.CharField(max_length=120, required=True)
    cedula = forms.CharField(max_length=20, required=True)
    plan = forms.ChoiceField(choices=[('', 'Sin plan')] + list(PerfilUsuario.Plan.choices), required=False)

    class Meta:
        model = get_user_model()
        fields = ('username', 'email', 'nombre', 'cedula', 'plan')

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
                    'plan': self.cleaned_data.get('plan', ''),
                },
            )
        return user


class PerfilForm(forms.ModelForm):
    class Meta:
        model = PerfilUsuario
        fields = ('nombre', 'foto')
        labels = {
            'nombre': 'Nombre',
            'foto': 'Foto de perfil',
        }


class HorarioDisponibleForm(forms.ModelForm):
    fecha = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    hora = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}))

    class Meta:
        model = HorarioDisponible
        fields = ('fecha', 'hora', 'disponible')


class EspecieForm(forms.ModelForm):
    foto = forms.ImageField(label='Foto de la especie', required=True)

    class Meta:
        model = Especie
        fields = ('nombre', 'foto')
        labels = {
            'nombre': 'Nombre de la especie',
        }


class FotoEspecieForm(forms.Form):
    foto = forms.ImageField(label='Foto de la especie', required=True)


class AsignarPlantaForm(forms.ModelForm):
    class Meta:
        model = Planta
        fields = ('usuario', 'especie', 'apodo')
        labels = {
            'usuario': 'Cliente',
            'especie': 'Especie del catálogo',
            'apodo': 'Nombre de la planta',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usuario'].queryset = get_user_model().objects.filter(is_staff=False).order_by('username')
        self.fields['especie'].queryset = Especie.objects.order_by('nombre')


class HorarioDisponibleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, horario):
        return f'{horario.fecha:%d/%m/%Y} - {horario.hora:%H:%M}'


class NuevaPlantaForm(forms.ModelForm):
    horario_disponible = HorarioDisponibleChoiceField(
        queryset=HorarioDisponible.objects.none(),
        label='Selecciona un horario disponible',
        empty_label='Selecciona fecha y hora',
    )

    class Meta:
        model = SolicitudPlanta
        fields = ('especie', 'apodo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['horario_disponible'].queryset = HorarioDisponible.objects.filter(
            disponible=True,
        ).order_by('fecha', 'hora')

    def save(self, commit=True):
        solicitud = super().save(commit=False)
        horario = self.cleaned_data['horario_disponible']
        solicitud.fecha_cita = horario.fecha
        solicitud.hora_cita = horario.hora
        if commit:
            solicitud.save()
            self.save_m2m()
        return solicitud
