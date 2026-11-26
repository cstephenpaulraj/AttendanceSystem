# AI-Driven Classroom Attendance System

Fixed-camera face recognition attendance for lecture halls: one edge AI unit per hall, with the college central server pulling attendance records through an API.

## Contents

| Path | What it is |
|---|---|
| [docs/Technology_Selection_Strategy.md](docs/Technology_Selection_Strategy.md) | Technology selection strategy for the edge AI software (enrolment and multi-face recognition): options, industry approaches, justification, licences and development approach |
| [architecture/technology_stack_pipeline.drawio](architecture/technology_stack_pipeline.drawio) | Technology stack and processing pipeline diagram (open in diagrams.net / draw.io) |
| [architecture/overall architecture.draw.io](architecture/overall%20architecture.draw.io) | Overall 5-hall system architecture diagram |
| [docs/PTZ_Implementation.md](docs/PTZ_Implementation.md) | PTZ taught-point concept (separate from the fixed-camera solution): design, supervised enrolment, sessions from the central system, RF fallback, lecturer override, face database protection, technology stack, demo status |
| architecture/PTZ_01 ... PTZ_04 .drawio | PTZ concept diagrams: overall architecture, technology stack, face enrolment workflow, attendance marking workflow |
| [ptz_laptop_demo/](ptz_laptop_demo/) | PTZ taught-point concept: runnable laptop demo of the five apps (supervised face capture, Enrolment Converter, Edge AI service, attendance with standby camera and RF fallback, college central system simulator) with photo simulation and a user guide ([USER_GUIDE.md](ptz_laptop_demo/USER_GUIDE.md)) |
