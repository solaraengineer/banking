from django import forms


class RegisterForm(forms.Form):
    first_name = forms.CharField(max_length=100,required=True)
    last_name = forms.CharField(max_length=100,required=True)
    email = forms.CharField(max_length=100,required=True)
    phone_number = forms.CharField(max_length=13,required=True)
    address = forms.CharField(max_length=100,required=True)
    city = forms.CharField(max_length=100,required=True)
    ZIP = forms.CharField(max_length=100,required=True)
    username = forms.CharField(max_length=100,required=True)
    password = forms.CharField(widget=forms.PasswordInput)

