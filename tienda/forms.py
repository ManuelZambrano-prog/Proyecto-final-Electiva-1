from django import forms
from .models import Pedido, ConsultaContacto, KitRiego


class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = [
            'kit',
            'nombre_completo',
            'email',
            'telefono',
            'ciudad',
            'direccion',
            'barrio',
            'plantas_en_casa',
            'tanque_extra',
            'sensores_extra',
            'metodo_pago',
            'notas',
        ]
        widgets = {
            'kit': forms.Select(attrs={'class': 'form-select', 'id': 'id_kit'}),
            'nombre_completo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: Juliana Escobar'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'correo@ejemplo.com'}),
            'telefono': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: 300 123 4567'}),
            'ciudad': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: Medellín / Bogotá / Cali'}),
            'direccion': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Calle, Carrera, Edificio, Apto'}),
            'barrio': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: El Poblado, Chapinero...'}),
            'plantas_en_casa': forms.NumberInput(attrs={'class': 'form-input', 'min': '1', 'max': '50', 'id': 'id_plantas_en_casa'}),
            'tanque_extra': forms.CheckboxInput(attrs={'class': 'form-checkbox', 'id': 'id_tanque_extra'}),
            'sensores_extra': forms.CheckboxInput(attrs={'class': 'form-checkbox', 'id': 'id_sensores_extra'}),
            'metodo_pago': forms.Select(attrs={'class': 'form-select'}),
            'notas': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Instrucciones especiales para entrega o detalles de tus plantas...'}),
        }


class ConsultaContactoForm(forms.ModelForm):
    class Meta:
        model = ConsultaContacto
        fields = ['nombre', 'email', 'telefono', 'tipo_consulta', 'mensaje']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Tu nombre completo'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'tu@email.com'}),
            'telefono': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Número de WhatsApp / Teléfono'}),
            'tipo_consulta': forms.Select(attrs={'class': 'form-select'}),
            'mensaje': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4, 'placeholder': 'Cuéntanos cuántas plantas tienes en casa, qué dudas tienes o cómo podemos ayudarte...'}),
        }
