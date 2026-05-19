from django import forms
from django.forms.models import BaseInlineFormSet

from .models import ProductImage


class ProductImageInlineForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ("image", "sort_order")
        widgets = {
            "sort_order": forms.HiddenInput(),
        }


class ProductImageInlineFormSet(BaseInlineFormSet):

    def _image_forms_in_saved_order(self):
        forms_with_images = []

        for form_index, form in enumerate(self.forms):
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if self._should_delete_form(form):
                continue

            has_existing_image = bool(form.instance.pk and form.instance.image)
            has_uploaded_image = bool(form.cleaned_data.get("image"))

            if not has_existing_image and not has_uploaded_image:
                continue

            raw_order = form.cleaned_data.get("sort_order")
            try:
                order = int(raw_order)
            except (TypeError, ValueError):
                order = form_index

            forms_with_images.append((order, form_index, form))

        forms_with_images.sort(key=lambda item: (item[0], item[1]))
        return [form for _, _, form in forms_with_images]

    def clean(self):
        super().clean()
        ordered_forms = self._image_forms_in_saved_order()

        for index, form in enumerate(ordered_forms):
            form.cleaned_data["sort_order"] = index
            form.instance.sort_order = index
            form.instance.is_main = index == 0

    def save(self, commit=True):
        ordered_forms = self._image_forms_in_saved_order()

        for index, form in enumerate(ordered_forms):
            form.cleaned_data["sort_order"] = index
            form.instance.sort_order = index
            form.instance.is_main = index == 0

        if commit and self.instance.pk:
            ProductImage.objects.filter(product=self.instance, is_main=True).update(is_main=False)

        return super().save(commit=commit)
