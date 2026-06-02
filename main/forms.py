from django import forms

from .models import ReturnRequest


class ReturnRequestForm(forms.ModelForm):
    class Meta:
        model = ReturnRequest
        fields = ("condition", "reason", "photo")
        widgets = {
            "condition": forms.Select(attrs={"class": "return-form-control"}),
            "reason": forms.Textarea(attrs={
                "class": "return-form-control",
                "rows": 5,
                "placeholder": "Опишите причину возврата: размер не подошёл, обнаружен дефект, товар не соответствует ожиданиям и т.д.",
            }),
            "photo": forms.ClearableFileInput(attrs={"class": "return-file-input"}),
        }
        labels = {
            "condition": "Состояние товара",
            "reason": "Причина возврата",
            "photo": "Фото товара, если нужно",
        }
        help_texts = {
            "photo": "Необязательно. Можно приложить фото дефекта или состояния товара.",
        }
