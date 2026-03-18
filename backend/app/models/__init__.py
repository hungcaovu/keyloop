from .customer import Customer
from .vehicle import Vehicle
from .dealership import Dealership
from .service_type import ServiceType
from .technician import Technician, TechnicianQualification
from .service_bay import ServiceBay
from .appointment import Appointment, AppointmentStatus

__all__ = [
    "Customer",
    "Vehicle",
    "Dealership",
    "ServiceType",
    "Technician",
    "TechnicianQualification",
    "ServiceBay",
    "Appointment",
    "AppointmentStatus",
]
