"""
Seed data for development and demo purposes.

Run via:
  flask seed-db         (inside Docker or local venv)
  docker compose exec app flask seed-db
"""

from datetime import datetime, timezone

from app.extensions import db
from app.models.customer import Customer
from app.models.vehicle import Vehicle
from app.models.dealership import Dealership
from app.models.service_type import ServiceType
from app.models.technician import Technician, TechnicianQualification
from app.models.service_bay import ServiceBay
from app.repositories.vehicle_repository import VehicleRepository


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_seed():
    """Insert all seed data. Idempotent — skips if data already exists."""

    # ── Service Types ──────────────────────────────────────────────────────────
    if ServiceType.query.count() == 0:
        service_types = [
            ServiceType(name="Oil Change",            description="Full synthetic oil change and filter replacement", duration_minutes=30,  required_bay_type="GENERAL"),
            ServiceType(name="Tire Rotation",         description="Rotate all four tires and check pressure",          duration_minutes=30,  required_bay_type="LIFT"),
            ServiceType(name="Brake Inspection",      description="Full brake system inspection and pad check",         duration_minutes=90,  required_bay_type="LIFT"),
            ServiceType(name="Brake Pad Replacement", description="Front or rear brake pad replacement",                duration_minutes=120, required_bay_type="LIFT"),
            ServiceType(name="Wheel Alignment",       description="4-wheel computerized alignment check and adjustment", duration_minutes=60,  required_bay_type="ALIGNMENT"),
            ServiceType(name="AC Service",            description="AC system check, recharge, and leak test",           duration_minutes=90,  required_bay_type="GENERAL"),
            ServiceType(name="Engine Diagnostics",    description="OBD-II scan and engine diagnostic report",           duration_minutes=60,  required_bay_type="GENERAL"),
            ServiceType(name="Transmission Service",  description="Transmission fluid flush and filter change",         duration_minutes=120, required_bay_type="LIFT"),
        ]
        db.session.add_all(service_types)
        db.session.flush()
        print(f"  Inserted {len(service_types)} service types")
    else:
        service_types = ServiceType.query.all()
        print(f"  Service types already exist ({len(service_types)} found), skipping")

    # Map name → object for easy reference below
    st_map = {st.name: st for st in service_types}

    # ── Dealerships ────────────────────────────────────────────────────────────
    if Dealership.query.count() == 0:
        dealerships = [
            Dealership(name="Metro Honda Service Center", address="1234 Main St",   city="Austin",        state="TX", timezone="America/Chicago"),
            Dealership(name="Metro Toyota of Austin",     address="5678 Oak Ave",   city="Austin",        state="TX", timezone="America/Chicago"),
            Dealership(name="Westside Ford Service",      address="901 West Blvd",  city="Los Angeles",   state="CA", timezone="America/Los_Angeles"),
            Dealership(name="Bay Area BMW",               address="42 Tech Pkwy",   city="San Francisco", state="CA", timezone="America/Los_Angeles"),
            Dealership(name="Manhattan Benz Service",     address="100 Park Ave",   city="New York",      state="NY", timezone="America/New_York"),
        ]
        db.session.add_all(dealerships)
        db.session.flush()
        print(f"  Inserted {len(dealerships)} dealerships")
    else:
        dealerships = Dealership.query.all()
        print(f"  Dealerships already exist ({len(dealerships)} found), skipping")

    d_map = {d.name: d for d in dealerships}

    # ── Service Bays ───────────────────────────────────────────────────────────
    if ServiceBay.query.count() == 0:
        bays = []
        for dealership in dealerships:
            # 3 LIFT bays, 2 GENERAL, 1 ALIGNMENT per dealership
            bay_config = [
                ("Bay 1", "LIFT"),
                ("Bay 2", "LIFT"),
                ("Bay 3", "LIFT"),
                ("Bay 4", "GENERAL"),
                ("Bay 5", "GENERAL"),
                ("Bay 6", "ALIGNMENT"),
                ("Bay 7", "GENERAL"),
                ("Bay 8", "GENERAL"),
                ("Bay 9", "GENERAL"),
                ("Bay 10", "GENERAL"),
            ]
            for bay_number, bay_type in bay_config:
                bays.append(ServiceBay(
                    dealership_id=dealership.id,
                    bay_number=bay_number,
                    bay_type=bay_type,
                    is_active=True,
                ))
        db.session.add_all(bays)
        db.session.flush()
        print(f"  Inserted {len(bays)} service bays")
    else:
        print(f"  Service bays already exist, skipping")

    # ── Technicians + Qualifications ───────────────────────────────────────────
    if Technician.query.count() == 0:
        all_techs = []
        emp_counter = 1

        # Technician templates per dealership (3-4 per dealership)
        tech_names = [
            ("Carlos", "Reyes"),
            ("Maria", "Santos"),
            ("James", "Okafor"),
            ("Sarah", "Kim"),
            ("David", "Nguyen"),
        ]

        for dealership in dealerships:
            for i, (first, last) in enumerate(tech_names[:4]):
                tech = Technician(
                    dealership_id=dealership.id,
                    first_name=first,
                    last_name=last,
                    employee_number=f"T-{emp_counter:03d}",
                    is_active=True,
                )
                all_techs.append(tech)
                emp_counter += 1

        db.session.add_all(all_techs)
        db.session.flush()
        print(f"  Inserted {len(all_techs)} technicians")

        # Qualifications: most techs are qualified for most services
        qualifications = []
        certified = _now()

        # Service types that require different skill levels
        basic_services   = ["Oil Change", "Tire Rotation", "Engine Diagnostics", "AC Service"]
        lift_services    = ["Brake Inspection", "Brake Pad Replacement", "Transmission Service"]
        align_services   = ["Wheel Alignment"]

        for tech in all_techs:
            # All technicians can do basic services
            for svc_name in basic_services:
                if svc_name in st_map:
                    qualifications.append(TechnicianQualification(
                        technician_id=tech.id,
                        service_type_id=st_map[svc_name].id,
                        certified_at=certified,
                    ))
            # First 3 techs per dealership also do lift services
            tech_idx = all_techs.index(tech) % 4
            if tech_idx < 3:
                for svc_name in lift_services:
                    if svc_name in st_map:
                        qualifications.append(TechnicianQualification(
                            technician_id=tech.id,
                            service_type_id=st_map[svc_name].id,
                            certified_at=certified,
                        ))
            # First tech per dealership is also alignment certified
            if tech_idx == 0:
                for svc_name in align_services:
                    if svc_name in st_map:
                        qualifications.append(TechnicianQualification(
                            technician_id=tech.id,
                            service_type_id=st_map[svc_name].id,
                            certified_at=certified,
                        ))

        db.session.add_all(qualifications)
        db.session.flush()
        print(f"  Inserted {len(qualifications)} technician qualifications")
    else:
        print(f"  Technicians already exist, skipping")

    # ── Customers ──────────────────────────────────────────────────────────────
    if Customer.query.count() == 0:
        customers = [
            Customer(first_name="Jane",   last_name="Smith",     email="jane.smith@example.com",  phone="+1-555-0101", created_at=_now()),
            Customer(first_name="John",   last_name="Doe",       email="john.doe@example.com",    phone="+1-555-0102", created_at=_now()),
            Customer(first_name="Alice",  last_name="Johnson",   email="alice.j@example.com",     phone="+1-555-0103", created_at=_now()),
            Customer(first_name="Bob",    last_name="Williams",  email="bob.w@example.com",       phone="+1-555-0104", created_at=_now()),
            Customer(first_name="Maria",  last_name="Garcia",    email="m.garcia@example.com",    phone="+1-555-0105", created_at=_now()),
            Customer(first_name="Wei",    last_name="Zhang",     email="wei.zhang@example.com",   phone="+1-555-0106", created_at=_now()),
            Customer(first_name="Fatima", last_name="Al-Rashid", email="f.alrashid@example.com",  phone="+1-555-0107", created_at=_now()),
            Customer(first_name="Marcus", last_name="Thompson",  email="m.thompson@example.com",  phone="+1-555-0108", created_at=_now()),
        ]
        db.session.add_all(customers)
        db.session.flush()
        print(f"  Inserted {len(customers)} customers")
    else:
        customers = Customer.query.all()
        print(f"  Customers already exist ({len(customers)} found), skipping")

    # ── Vehicles ───────────────────────────────────────────────────────────────
    if Vehicle.query.count() == 0 and customers:
        vehicle_repo = VehicleRepository()

        # Vehicles with VIN — inserted directly (no vehicle_number needed)
        vehicles_with_vin = [
            Vehicle(customer_id=customers[0].id, vin="1HGCM82633A123456", make="Honda",      model="Accord",   year=2022, created_at=_now()),
            Vehicle(customer_id=customers[1].id, vin="2T1BURHE0JC034521", make="Toyota",     model="Corolla",  year=2018, created_at=_now()),
            Vehicle(customer_id=customers[2].id, vin="1FTFW1ET5DFC10312", make="Ford",       model="F-150",    year=2020, created_at=_now()),
            Vehicle(customer_id=customers[3].id, vin="WBA3A5G59DNP26082", make="BMW",        model="3 Series", year=2019, created_at=_now()),
            Vehicle(customer_id=customers[4].id, vin="JN1AZ4EH4FM730841", make="Nissan",     model="370Z",     year=2021, created_at=_now()),
            Vehicle(customer_id=customers[5].id, vin="WVWZZZ1JZXW000001", make="Volkswagen", model="Golf",     year=2023, created_at=_now()),
            Vehicle(customer_id=customers[6].id, vin="5YJSA1E26MF464820", make="Tesla",      model="Model S",  year=2021, created_at=_now()),
        ]
        db.session.add_all(vehicles_with_vin)
        db.session.flush()

        # Vehicle without VIN — use repo so vehicle_number is auto-assigned
        vehicle_repo.create(
            customer_id=customers[0].id,
            make="Honda",
            model="Civic",
            year=2024,
            vin=None,
        )

        total = len(vehicles_with_vin) + 1
        print(f"  Inserted {total} vehicles")
    else:
        print(f"  Vehicles already exist, skipping")

    db.session.commit()
    print("\nSeed data committed successfully.")
    print("\nSample IDs for testing:")
    if dealerships:
        d = dealerships[0]
        print(f"  Dealership: {d.name}")
        print(f"    id: {d.id}")
    if service_types:
        for st in service_types[:3]:
            print(f"  ServiceType '{st.name}': id={st.id}")
    if customers:
        c = customers[0]
        print(f"  Customer '{c.first_name} {c.last_name}': id={c.id}")
        vehicles = Vehicle.query.filter_by(customer_id=c.id).all()
        for v in vehicles:
            ref = f"V-{v.vehicle_number:06d}" if v.vehicle_number else f"VIN:{v.vin}"
            print(f"    Vehicle {v.year} {v.make} {v.model}: id={v.id}, ref={ref}")
