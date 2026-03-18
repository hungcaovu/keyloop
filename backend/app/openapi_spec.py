"""
OpenAPI 3.1 specification for the Unified Service Scheduler API.
Served at /openapi.json; Swagger UI at /swagger-ui.
"""

SPEC: dict = {
    "openapi": "3.1.0",
    "info": {
        "title": "Unified Service Scheduler",
        "version": "v1",
        "description": (
            "Backend API for scheduling automotive service appointments.\n\n"
            "**Status legend:**\n"
            "- ✅ Endpoints with no badge are **implemented and available** in the current build.\n"
            "- 🚧 Endpoints tagged **planned** are designed and documented but **not yet implemented**."
        ),
    },
    "servers": [{"url": "/", "description": "Current server"}],
    "tags": [
        {"name": "customers",      "description": "Customer management"},
        {"name": "vehicles",       "description": "Vehicle registry"},
        {"name": "appointments",   "description": "Appointment booking & management"},
        {"name": "availability",   "description": "Calendar & slot availability"},
        {"name": "dealerships",    "description": "Dealerships, technicians & bays"},
        {"name": "service-types",  "description": "Service type catalogue"},
        {"name": "system",         "description": "Health & diagnostics"},
        {
            "name": "planned",
            "description": "🚧 **Planned — not yet implemented.** These endpoints are designed and documented but not available in the current build.",
        },
    ],
    "components": {
        "schemas": {
            "Customer": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "readOnly": True},
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "phone": {"type": ["string", "null"]},
                    "address_line1": {"type": ["string", "null"]},
                    "address_line2": {"type": ["string", "null"]},
                    "city": {"type": ["string", "null"]},
                    "state": {"type": ["string", "null"]},
                    "postal_code": {"type": ["string", "null"]},
                    "country": {"type": ["string", "null"]},
                    "created_at": {"type": "string", "format": "date-time", "readOnly": True},
                },
            },
            "CustomerCreate": {
                "type": "object",
                "required": ["first_name", "last_name", "email"],
                "properties": {
                    "first_name": {"type": "string", "maxLength": 100},
                    "last_name": {"type": "string", "maxLength": 100},
                    "email": {"type": "string", "format": "email"},
                    "phone": {"type": "string", "maxLength": 30},
                    "address_line1": {"type": "string", "maxLength": 255},
                    "address_line2": {"type": "string", "maxLength": 255},
                    "city": {"type": "string", "maxLength": 100},
                    "state": {"type": "string", "maxLength": 100},
                    "postal_code": {"type": "string", "maxLength": 20},
                    "country": {"type": "string", "maxLength": 100, "default": "US"},
                },
            },
            "CustomerUpdate": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string", "maxLength": 100},
                    "last_name": {"type": "string", "maxLength": 100},
                    "email": {"type": "string", "format": "email"},
                    "phone": {"type": ["string", "null"], "maxLength": 30},
                    "address_line1": {"type": ["string", "null"], "maxLength": 255},
                    "address_line2": {"type": ["string", "null"], "maxLength": 255},
                    "city": {"type": ["string", "null"], "maxLength": 100},
                    "state": {"type": ["string", "null"], "maxLength": 100},
                    "postal_code": {"type": ["string", "null"], "maxLength": 20},
                    "country": {"type": ["string", "null"], "maxLength": 100},
                },
            },
            "Vehicle": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "readOnly": True},
                    "customer_id": {"type": "integer"},
                    "vehicle_number": {"type": ["integer", "null"], "readOnly": True},
                    "vehicle_ref": {
                        "type": ["string", "null"],
                        "example": "V-000001",
                        "description": "Human-readable reference for VIN-less vehicles (V-XXXXXX)",
                        "readOnly": True,
                    },
                    "vin": {"type": ["string", "null"], "maxLength": 17},
                    "make": {"type": "string"},
                    "model": {"type": "string"},
                    "year": {"type": "integer"},
                    "color": {"type": ["string", "null"]},
                    "license_plate": {"type": ["string", "null"]},
                    "created_at": {"type": "string", "format": "date-time", "readOnly": True},
                },
            },
            "VehicleCreate": {
                "type": "object",
                "required": ["customer_id", "make", "model", "year"],
                "properties": {
                    "customer_id": {"type": "integer"},
                    "vin": {"type": "string", "maxLength": 17},
                    "make": {"type": "string", "maxLength": 100},
                    "model": {"type": "string", "maxLength": 100},
                    "year": {"type": "integer", "minimum": 1900, "maximum": 2100},
                    "color": {"type": "string", "maxLength": 50},
                    "license_plate": {"type": "string", "maxLength": 20},
                },
            },
            "Appointment": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "readOnly": True},
                    "dealership_id": {"type": "integer"},
                    "customer_id": {"type": "integer"},
                    "vehicle_id": {"type": "integer"},
                    "technician_id": {"type": ["integer", "null"]},
                    "bay_id": {"type": ["integer", "null"]},
                    "service_type_id": {"type": "integer"},
                    "booked_by_customer_id": {"type": ["integer", "null"]},
                    "start_time": {"type": "string", "format": "date-time"},
                    "end_time": {"type": "string", "format": "date-time"},
                    "status": {
                        "type": "string",
                        "enum": ["scheduled", "in_progress", "completed", "cancelled"],
                    },
                    "notes": {"type": ["string", "null"]},
                    "created_at": {"type": "string", "format": "date-time", "readOnly": True},
                },
            },
            "AppointmentCreate": {
                "type": "object",
                "required": ["dealership_id", "customer_id", "vehicle_id", "service_type_id", "start_time"],
                "properties": {
                    "dealership_id": {"type": "integer"},
                    "customer_id": {"type": "integer"},
                    "vehicle_id": {
                        "type": "string",
                        "description": "Integer ID, VH-XXXXXX, 17-char VIN, or V-XXXXXX vehicle ref",
                    },
                    "service_type_id": {"type": "integer"},
                    "start_time": {"type": "string", "format": "date-time"},
                    "technician_id": {"type": "integer"},
                    "booked_by_customer_id": {"type": "integer"},
                    "notes": {"type": "string"},
                },
            },
            "AvailabilitySlot": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "format": "date-time"},
                    "end": {"type": "string", "format": "date-time"},
                    "technician_id": {"type": "integer"},
                    "bay_id": {"type": "integer"},
                },
            },
            "Dealership": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "timezone": {"type": "string", "example": "America/Chicago"},
                    "business_hours_start": {"type": "string", "example": "08:00"},
                    "business_hours_end": {"type": "string", "example": "18:00"},
                    "slot_duration_minutes": {"type": "integer"},
                    "lead_time_minutes": {"type": "integer"},
                    "max_days_advance": {"type": "integer"},
                },
            },
            "ServiceType": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "bay_type": {"type": "string"},
                },
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "details": {"type": "object"},
                },
            },
            "DuplicatePhoneWarning": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "example": "DUPLICATE_PHONE"},
                    "message": {"type": "string"},
                    "existing_customer": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                        },
                    },
                },
            },
        }
    },
    "paths": {
        "/health": {
            "get": {
                "tags": ["system"],
                "summary": "Health check",
                "operationId": "health_check",
                "responses": {
                    "200": {
                        "description": "Service is healthy",
                        "content": {
                            "application/json": {
                                "example": {"status": "ok", "service": "unified-service-scheduler"}
                            }
                        },
                    }
                },
            }
        },
        "/customers": {
            "get": {
                "tags": ["customers"],
                "summary": "Search customers by phone or name",
                "operationId": "search_customers",
                "parameters": [
                    {
                        "name": "phone",
                        "in": "query",
                        "schema": {"type": "string"},
                        "example": "+1-555-0101",
                    },
                    {
                        "name": "q",
                        "in": "query",
                        "description": "Name search (min 2 chars)",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 10},
                    },
                    {
                        "name": "cursor",
                        "in": "query",
                        "description": "Opaque cursor for next page (from `next_cursor` in previous response). Only applies to name search (`q`).",
                        "schema": {"type": "string"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "List of matching customers",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "data": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Customer"},
                                        },
                                        "next_cursor": {
                                            "type": ["string", "null"],
                                            "description": "Pass as `cursor` to fetch the next page. `null` means no more pages.",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Missing or invalid query params"},
                },
            },
            "post": {
                "tags": ["customers"],
                "summary": "Create a new customer",
                "operationId": "create_customer",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CustomerCreate"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Customer created",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "customer": {"$ref": "#/components/schemas/Customer"},
                                        "warning": {"$ref": "#/components/schemas/DuplicatePhoneWarning"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Validation error"},
                    "409": {"description": "Email already exists"},
                },
            },
        },
        "/customers/{customer_id}": {
            "get": {
                "tags": ["customers"],
                "summary": "Get customer by ID",
                "operationId": "get_customer",
                "parameters": [
                    {"name": "customer_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {
                        "name": "include",
                        "in": "query",
                        "description": "Comma-separated list of sub-resources to embed. Supported: vehicles",
                        "schema": {"type": "string"},
                        "example": "vehicles",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Customer object (with optional embedded vehicles)",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "customer": {"$ref": "#/components/schemas/Customer"}
                                    },
                                }
                            }
                        },
                    },
                    "404": {"description": "Customer not found"},
                },
            },
            "patch": {
                "tags": ["customers"],
                "summary": "Update customer fields",
                "operationId": "update_customer",
                "parameters": [
                    {"name": "customer_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CustomerUpdate"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Updated customer",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "customer": {"$ref": "#/components/schemas/Customer"},
                                        "warning": {"$ref": "#/components/schemas/DuplicatePhoneWarning"},
                                    },
                                }
                            }
                        },
                    },
                    "404": {"description": "Customer not found"},
                    "409": {"description": "Email conflict"},
                },
            },
        },
        "/vehicles": {
            "post": {
                "tags": ["vehicles"],
                "summary": "Register a vehicle",
                "operationId": "create_vehicle",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/VehicleCreate"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Vehicle registered. VIN-less vehicles receive a V-XXXXXX vehicle_ref.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"vehicle": {"$ref": "#/components/schemas/Vehicle"}},
                                }
                            }
                        },
                    },
                    "400": {"description": "Validation error"},
                    "404": {"description": "Customer not found"},
                    "409": {"description": "VIN already registered"},
                },
            }
        },
        "/vehicles/{identifier}": {
            "get": {
                "tags": ["vehicles"],
                "summary": "Get vehicle by ID, VIN, or V-XXXXXX ref",
                "operationId": "get_vehicle",
                "parameters": [
                    {
                        "name": "identifier",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Numeric ID (or VH-XXXXXX format), VIN (17-char), or V-XXXXXX vehicle reference",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Vehicle object",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"vehicle": {"$ref": "#/components/schemas/Vehicle"}},
                                }
                            }
                        },
                    },
                    "404": {"description": "Vehicle not found"},
                },
            },
            "patch": {
                "tags": ["vehicles"],
                "summary": "Update vehicle fields",
                "operationId": "update_vehicle",
                "parameters": [
                    {"name": "identifier", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "responses": {
                    "200": {"description": "Updated vehicle"},
                    "404": {"description": "Vehicle not found"},
                    "409": {"description": "VIN conflict"},
                },
            },
        },
        "/appointments": {
            "post": {
                "tags": ["appointments"],
                "summary": "Book an appointment",
                "operationId": "create_appointment",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/AppointmentCreate"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Appointment booked",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"appointment": {"$ref": "#/components/schemas/Appointment"}},
                                }
                            }
                        },
                    },
                    "400": {"description": "Validation / business rule error (outside hours, lead time, etc.)"},
                    "404": {"description": "Referenced entity not found"},
                    "409": {"description": "Scheduling conflict"},
                },
            }
        },
        "/appointments/{appointment_id}": {
            "get": {
                "tags": ["appointments", "planned"],
                "summary": "Get appointment by ID",
                "description": "🚧 **Planned — not yet implemented.**",
                "operationId": "get_appointment",
                "parameters": [
                    {"name": "appointment_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {"description": "Appointment object"},
                    "404": {"description": "Not found"},
                },
            },
            "patch": {
                "tags": ["appointments", "planned"],
                "summary": "Update appointment (reschedule / change status)",
                "description": "🚧 **Planned — not yet implemented.**",
                "operationId": "update_appointment",
                "parameters": [
                    {"name": "appointment_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "responses": {
                    "200": {"description": "Updated appointment"},
                    "400": {"description": "Validation error"},
                    "404": {"description": "Not found"},
                    "409": {"description": "Conflict"},
                },
            },
            "delete": {
                "tags": ["appointments", "planned"],
                "summary": "Cancel / delete appointment",
                "description": "🚧 **Planned — not yet implemented.**",
                "operationId": "delete_appointment",
                "parameters": [
                    {"name": "appointment_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "204": {"description": "Deleted"},
                    "404": {"description": "Not found"},
                },
            },
        },
        "/dealerships/{dealership_id}/availability": {
            "get": {
                "tags": ["availability"],
                "summary": "Get available appointment slots for a date range",
                "operationId": "get_availability",
                "parameters": [
                    {"name": "dealership_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {
                        "name": "service_type_id",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "date_from",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string", "format": "date"},
                        "example": "2026-04-01",
                    },
                    {
                        "name": "date_to",
                        "in": "query",
                        "schema": {"type": "string", "format": "date"},
                        "example": "2026-04-07",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Available slots grouped by date",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/AvailabilitySlot"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Invalid parameters"},
                    "404": {"description": "Dealership not found"},
                },
            }
        },
        "/dealerships": {
            "get": {
                "tags": ["dealerships"],
                "summary": "List all dealerships",
                "operationId": "list_dealerships",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "description": "Name search (min 2 chars)",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 10},
                    },
                    {
                        "name": "cursor",
                        "in": "query",
                        "description": "Opaque cursor for next page (from `next_cursor` in previous response).",
                        "schema": {"type": "string"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "List of dealerships",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "data": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Dealership"},
                                        },
                                        "next_cursor": {
                                            "type": ["string", "null"],
                                            "description": "Pass as `cursor` to fetch the next page. `null` means no more pages.",
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/dealerships/{dealership_id}/technicians": {
            "get": {
                "tags": ["dealerships"],
                "summary": "List technicians at a dealership",
                "operationId": "list_technicians",
                "parameters": [
                    {"name": "dealership_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {"200": {"description": "List of technicians"}},
            }
        },
        "/dealerships/{dealership_id}/bays": {
            "get": {
                "tags": ["dealerships", "planned"],
                "summary": "List service bays at a dealership",
                "description": "🚧 **Planned — not yet implemented.**",
                "operationId": "list_bays",
                "parameters": [
                    {"name": "dealership_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {"200": {"description": "List of bays"}},
            }
        },
        "/service-types": {
            "get": {
                "tags": ["service-types"],
                "summary": "List all service types",
                "operationId": "list_service_types",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "description": "Name/description search (min 2 chars)",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 20},
                    },
                    {
                        "name": "cursor",
                        "in": "query",
                        "description": "Opaque cursor for next page (from `next_cursor` in previous response).",
                        "schema": {"type": "string"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "List of service types",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "data": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/ServiceType"},
                                        },
                                        "next_cursor": {
                                            "type": ["string", "null"],
                                            "description": "Pass as `cursor` to fetch the next page. `null` means no more pages.",
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
    },
}
