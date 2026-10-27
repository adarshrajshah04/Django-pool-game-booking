from datetime import date

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from .models import *


# Custom select widget to disable the placeholder option
class DisabledPlaceholderSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value == "":
            option["attrs"]["disabled"] = True
        return option

# Registration form
class RegistrationForm(UserCreationForm):
    GENDER_CHOICES = [
        ("", "Select your gender"),
        ('Male', 'Male'),
        ('Female', 'Female')
    ]
    email = forms.EmailField(required= True)
    phone = forms.CharField(max_length=15, required=True)
    age = forms.IntegerField(required=True)
    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        required=True,
        initial="",
        widget=DisabledPlaceholderSelect,
    )
    profile_image = forms.ImageField(required=True)
    
    class Meta:
        model=User
        fields = [
            "first_name",
            "last_name",
            "username",
            "age",
            "gender",
            "email",
            "phone",
            "profile_image",
            "password1",
            "password2",
        ]
        
        

class PlanForm(forms.Form):
    WEEKDAY_CHOICES = (
        ("0", "Monday"),
        ("1", "Tuesday"),
        ("2", "Wednesday"),
        ("3", "Thursday"),
        ("4", "Friday"),
        ("5", "Saturday"),
        ("6", "Sunday"),
    )

    plan = forms.ChoiceField(
        choices=PlanModel.PLAN_CHOICES,
        required=True,
        widget=forms.HiddenInput(),
    )
    time_Slot = forms.ChoiceField(
    choices=[
        ("", "Select your time slot"),
        *PlanModel.TIME_SLOT_CHOICES,
    ],
    required=True,
    initial="",
    widget=DisabledPlaceholderSelect(
        attrs={"class": "form-control"}
    ),
)
    date = forms.DateField(
        required=False,
        widget=forms.HiddenInput(attrs={"min": timezone.localdate().isoformat()}),
    )
    weekdays = forms.CharField(required=False, widget=forms.HiddenInput())
    custom_dates = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean(self):
        cleaned_data = super().clean()
        plan = cleaned_data.get("plan")
        start_date = cleaned_data.get("date")
        today = timezone.localdate()

        # Basic and Monthly need a calendar anchor date.
        if plan in ("basic", "monthly"):
            if not start_date:
                self.add_error("date", "Choose a start date in the calendar.")
            elif start_date < today:
                self.add_error("date", "Choose today or a future date.")

        # Weekdays are relevant ONLY to Monthly.
        raw_weekdays = cleaned_data.get("weekdays", "")
        weekdays = [
            value.strip()
            for value in raw_weekdays.split(",")
            if value.strip()
        ] if raw_weekdays else []

        if plan == "monthly":
            valid_weekdays = {str(day) for day in range(7)}
            if (
                len(weekdays) != 2
                or len(set(weekdays)) != 2
                or not set(weekdays).issubset(valid_weekdays)
            ):
                self.add_error(
                    "weekdays",
                    "Select exactly two different weekdays for the Monthly Plan."
                )
            cleaned_data["weekdays"] = weekdays
        else:
            # Ignore stale hidden weekday values after switching plans.
            cleaned_data["weekdays"] = []

        # Custom dates are relevant ONLY to Custom.
        raw_dates = cleaned_data.get("custom_dates", "")
        date_values = [
            value.strip()
            for value in raw_dates.split(",")
            if value.strip()
        ] if raw_dates else []

        if plan == "custom":
            if (
                not 1 <= len(date_values) <= PlanModel.CUSTOM_BOOKING_LIMIT
                or len(set(date_values)) != len(date_values)
            ):
                self.add_error(
                    "custom_dates",
                    f"Choose between 1 and {PlanModel.CUSTOM_BOOKING_LIMIT} different dates."
                )
            else:
                try:
                    parsed_dates = [
                        date.fromisoformat(value)
                        for value in date_values
                    ]
                except ValueError:
                    self.add_error(
                        "custom_dates",
                        "One or more selected dates are invalid."
                    )
                else:
                    if any(selected_date < today for selected_date in parsed_dates):
                        self.add_error(
                            "custom_dates",
                            "Choose today or future dates."
                        )
                    cleaned_data["custom_dates"] = parsed_dates
        else:
            # Ignore stale custom dates after switching plans.
            cleaned_data["custom_dates"] = []

        return cleaned_data


# # update booking model

# class BookingUpdateForm(forms.ModelForm):
    
#     class Meta:
#         model = PlanModel
#         fields = 
