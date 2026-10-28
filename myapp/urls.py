from django.urls import path
from .views import *



urlpatterns = [
    path('', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', register, name='register'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('dashboard/holidays/', dashboard_holidays, name='dashboard_holidays'),
    path('booking/', selectPlan, name='booking'),
    path('payment/<int:booking_id>/', payment_view, name='payment'),
    path("payment/<int:booking_id>/verify/",verify_payment,name="verify_payment",),
    path("booking-details/", booking_detail, name="booking_detail"),
    path("booking-action/<int:id>/", bookingAction, name="bookingAction"),
    path("booking-canceling/<int:id>/", deleteBooking, name="booking-canceling"),
]