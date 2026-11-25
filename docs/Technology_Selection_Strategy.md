# AI-Driven Classroom Attendance System
## Technology Selection Strategy: Edge AI Software

| | |
|---|---|
| **Scope** | Software on the edge AI unit (one per lecture hall, 5 halls): enrolling each person, then finding and recognising every person in each camera frame |
| **Solution** | Fixed-camera solution (6 cameras per 300-seat hall, as in BOM_stage1_v6). The PTZ taught-point concept is out of scope for this report. |
| **Diagram** | [`architecture/technology_stack_pipeline.drawio`](../architecture/technology_stack_pipeline.drawio) |
| **Date** | 25 November 2026 |
| **Status** | Draft for review |

---

## 1. Summary

The fundamental job of the edge software is two things:

1. **Enrolment**: capture each student once under controlled conditions and store a mathematical "face template" (an embedding vector), not just a photo.
2. **Recognition in a crowd**: in every camera frame, find all faces (5 or 6 in a close-up, 50 or more in a wide shot of a zone), and match each one against the enrolled roster.

Modern systems from every serious vendor solve this with the same four-stage pipeline: **detect → align → embed → match**, plus **tracking** and **multi-frame voting** for reliability. The choice is not which pipeline to use, but which component and which licence to use at each stage.

**Recommendation (consistent with the BOM decision of AI licences at ₹0):**

| Stage | Selected technology | Licence | Fallback if the pilot fails |
|---|---|---|---|
| Video decode | GStreamer with NVIDIA hardware decoder (NVDEC) on Jetson | LGPL / free NVIDIA SDK | NVIDIA DeepStream |
| Face detection | **OpenCV YuNet** (with frame tiling for back rows) | MIT | Commercially licensed SCRFD / RetinaFace model, or commercial SDK |
| Alignment | 5-point landmarks from YuNet, similarity transform to 112 × 112 | (part of OpenCV) | |
| Face embedding | **OpenCV SFace** (ArcFace-family training) | Apache-2.0 | **InsightFace commercial licence** (ArcFace R100 / buffalo_l class models) or commercial SDK |
| Inference runtime | **TensorRT** (FP16) via **ONNX** models; ONNX Runtime for development on PCs | Free NVIDIA SDK / MIT | |
| Tracking | **ByteTrack** | MIT | |
| Matching | **FAISS** (cosine similarity on normalised vectors) | MIT | NumPy brute force (enough for a few thousand students) |
| Liveness (enrolment) | Passive anti-spoofing model (e.g. MiniVision Silent-Face) | Apache-2.0 | Commercial liveness SDK |
| Application | Python 3, FastAPI (pull API for the college server), SQLite with store-and-forward, Docker | Open source | |

The design keeps every model behind an **ONNX interface**, so swapping YuNet/SFace for a licensed InsightFace model or a commercial engine is a configuration change, not a rewrite. That is the core of the strategy: **start with zero-cost, commercially safe models; measure them on our own classroom data; upgrade only the stage that fails.**

---

## 2. Requirements that drive the choice

| # | Requirement | Why it matters for technology choice |
|---|---|---|
| R1 | Recognise many faces per frame (5 or 6 in a tight view, up to about 50 per camera zone) | Needs a multi-face detector, not a 1:1 "look at the terminal" device |
| R2 | Back-row faces are small (a 300-seat hall is about 20 rows deep) | Detector must find small faces; we must tile high-resolution frames rather than shrink them |
| R3 | Open-set 1:N identification against the whole roster (students roam between halls) | Needs a strong embedding model and a calibrated "unknown" threshold |
| R4 | Runs fully on the edge AI unit (Jetson Orin class), offline capable | Models must convert to TensorRT/ONNX; cloud APIs are excluded |
| R5 | Commercial use in a college deployment | Every model and library must allow commercial use (see Section 6) |
| R6 | Privacy under India's DPDP Act 2023 | Store embeddings encrypted, keep images local, consent at enrolment, delete on request |
| R7 | False "present" marks are worse than misses (a miss can be corrected by the lecturer) | Use strict thresholds plus multi-frame voting across the lecture |
| R8 | Maintainable by a small in-house team | Prefer widely used, documented open-source libraries with Python APIs |

---

## 3. How existing companies approach it

### 3.1 Two families of products

| Family | Examples | How it works | Fit for our classroom |
|---|---|---|---|
| **1:1 or 1:N terminals** (walk-up devices) | ZKTeco, eSSL (India), Hikvision MinMoe, Suprema FaceStation, Aadhaar-based AEBAS face authentication | One person stands in front of a device at 0.3 to 1.5 m; the device takes a large, frontal face | **Poor**. 300 students queueing at a device wastes lecture time. This is the "single gate" approach the project has moved away from. |
| **Crowd / CCTV recognition** (many faces per frame) | NEC NeoFace Watch, IDEMIA, Cognitec FaceVACS-VideoScan, Paravision, CyberLink FaceMe (has a Jetson edge SDK), Neurotechnology VeriLook, Hikvision DeepinView and Dahua AI cameras, NVIDIA Metropolis partner products | Cameras watch a scene; software detects every face, tracks it over time, picks the best-quality frames and searches a gallery | **Good**. This is the family our fixed-camera design belongs to. |

Cloud services such as AWS Rekognition and Azure Face follow the same pipeline but run in the cloud. Azure Face identification has been a Limited Access service since 2022. Both are excluded here because of R4 (offline) and R6 (student biometrics leaving campus), and because they are a recurring per-image cost.

### 3.2 What the crowd-recognition vendors have in common

Although their models are proprietary, published papers, product documentation and the NIST Face Recognition Technology Evaluation (FRTE, formerly FRVT) show a common recipe:

1. **CNN face detector** of the RetinaFace / SCRFD / YOLO-face family, run at high resolution or on tiles.
2. **Landmark alignment** to a fixed 112 × 112 crop.
3. **Margin-based embedding model** (ArcFace, CosFace, AdaFace style losses on ResNet or MobileFaceNet backbones), producing a 128 to 512 number vector.
4. **Tracking** (SORT / ByteTrack style) so each person is followed across frames.
5. **Quality scoring** (face size, sharpness, head pose) to choose the best frames.
6. **Gallery search** by cosine similarity, often with an approximate-nearest-neighbour index for large galleries.
7. **Decision over time**: identity is confirmed only after several consistent matches, not from one frame.
8. **Hardware acceleration** on the edge (TensorRT on NVIDIA, OpenVINO on Intel, NPU SDKs on camera chips).

Our design copies this recipe exactly, using open-source components at each step. The difference between vendors is mostly the **quality of the trained models** (training data size) and **engineering polish**, which is why the strategy keeps a commercial model as a fallback.

---

## 4. Candidate technologies evaluated

### 4.1 Face detection

| Option | Strengths | Weaknesses | Licence | Verdict |
|---|---|---|---|---|
| **OpenCV YuNet** | Very small (about 75k parameters), fast on CPU and GPU, gives 5 landmarks, built into OpenCV 4.8+ | Weaker on very small faces than large detectors (published WIDER FACE hard-set AP about 0.75); needs tiling for back rows | MIT | **Selected** (with tiling) |
| SCRFD (InsightFace) | Excellent speed/accuracy trade-off, strong on small faces (hard-set AP about 0.83 for the 10G model) | Pretrained weights are **non-commercial** | Code MIT, weights non-commercial | Fallback via commercial licence |
| RetinaFace (ResNet-50) | Among the most accurate public detectors (hard-set AP about 0.90 with multi-scale testing) | Heavier; popular weights are research-only | Varies by weight source | Fallback via licensed weights |
| YOLOv8/v11-face (Ultralytics) | Fast, easy to train | Ultralytics code and weights are **AGPL-3.0**: the whole application would have to be open-sourced, or an enterprise licence bought | AGPL-3.0 | Not selected |
| MTCNN | Classic, simple | Slow with many faces, less accurate than modern detectors | MIT (common ports) | Not selected |
| dlib HOG / CNN | Simple Python API | HOG misses small and turned faces; CNN detector is slow without heavy GPU work | Boost | Not selected |

Published accuracy figures above are approximate and come from each project's own documentation; Section 7 measures them on our halls.

### 4.2 Face recognition (embedding)

| Option | Strengths | Weaknesses | Licence | Verdict |
|---|---|---|---|---|
| **OpenCV SFace** | ArcFace-family model, about 99.4% on LFW (published), tiny and fast, ONNX ready, built into OpenCV | Lower accuracy than large ArcFace models on difficult (small, side-on, low-light) faces | Apache-2.0 | **Selected** |
| InsightFace ArcFace (R50/R100, buffalo_l, antelopev2) | De-facto industry reference; about 99.8% on LFW and strong on harder benchmarks | Pretrained models are **non-commercial research only**; commercial use needs a paid licence from InsightFace | Code MIT, models non-commercial | **Fallback** (paid licence) |
| FaceNet (open-source ports) | Well known | Older; outperformed by ArcFace-style models | MIT (ports) | Not selected |
| dlib / `face_recognition` | Easiest Python API (a few lines of code) | 128-d model from 2017, weaker on non-frontal and small faces; CPU-bound; not designed for 50 faces per frame | MIT / Boost | Prototyping only |
| DeepFace (Python wrapper) | One API over many models | A wrapper: licence of each wrapped model still applies; extra overhead | MIT (wrapper) | Not selected |
| Train our own ArcFace model | Full ownership | Needs millions of licensed face images; the big public datasets (MS1M, WebFace, Glint360K) are research-only | | Not selected |
| Commercial SDK (Paravision, CyberLink FaceMe, Neurotechnology, Cognitec) | Top NIST FRTE results, support, liveness included | Per-camera or per-device licence fees; vendor lock-in | Commercial | **Fallback** |

### 4.3 Runtime, acceleration and supporting libraries

| Area | Options considered | Selected | Reason |
|---|---|---|---|
| Inference engine | TensorRT, ONNX Runtime, OpenVINO, PyTorch | **TensorRT** on Jetson; **ONNX Runtime** on development PCs | TensorRT gives the best speed on NVIDIA Jetson (FP16); ONNX is the common model format so models stay portable. OpenVINO is the equivalent choice if an Intel edge box is ever used. |
| Video pipeline | OpenCV `VideoCapture`, GStreamer, NVIDIA DeepStream | **GStreamer with NVDEC** (DeepStream as an option) | Hardware decoding of six 8 MP RTSP streams frees the GPU/CPU. DeepStream adds batching and tracking but has a steeper learning curve; adopt it only if throughput requires it. |
| Tracking | SORT, DeepSORT, ByteTrack, NvDCF (DeepStream) | **ByteTrack** | Simple, accurate, MIT; keeps one identity per person across frames for voting |
| Vector search | FAISS, Annoy, hnswlib, NumPy | **FAISS** (flat inner-product index) | Exact search over about 2,500 students × 5 templates takes well under a millisecond; FAISS scales if the whole college is added |
| Liveness | MiniVision Silent-Face, commercial SDKs | **Silent-Face** at enrolment | Enrolment is where a photo or screen attack matters most. In class, multi-frame tracking plus the lecturer's view make photo attacks impractical. |
| Image processing | OpenCV | **OpenCV** | Industry standard, Apache-2.0, CUDA builds available on Jetson |
| Application and API | Flask, FastAPI, Node.js | **Python 3 + FastAPI** | Same language as the AI stack; FastAPI generates the OpenAPI document the college IT team needs for its pull API |
| Local storage | SQLite, PostgreSQL | **SQLite** on each edge unit | Zero administration; store-and-forward until the college server pulls |
| Packaging | Bare install, Docker | **Docker** (NVIDIA L4T base images) | Same image on all 5 units; easy update and rollback |

---

## 5. Justification for the selection

### 5.1 Scoring

Each criterion is scored 1 (poor) to 5 (excellent), then weighted.

| Criterion (weight) | YuNet + SFace (selected) | InsightFace licensed | Commercial SDK | dlib / face_recognition | Cloud API |
|---|---|---|---|---|---|
| Accuracy on small/difficult faces (30%) | 3 | 5 | 5 | 2 | 4 |
| Licence safety and cost (25%) | 5 | 3 | 2 | 5 | 2 |
| Edge performance on Jetson (15%) | 5 | 4 | 4 | 2 | 1 |
| Privacy / offline operation (10%) | 5 | 5 | 5 | 5 | 1 |
| No vendor lock-in (10%) | 5 | 4 | 1 | 5 | 1 |
| Ease of development and community (10%) | 4 | 4 | 3 | 5 | 4 |
| **Weighted score (out of 5)** | **4.30** | **4.15** | **3.50** | **3.65** | **2.45** |

YuNet + SFace and a licensed InsightFace model are close. The selected stack wins on cost and licence safety, while the licensed InsightFace model wins on accuracy. That is exactly why the plan starts with YuNet + SFace and uses a measured pilot to decide whether the accuracy gain is worth paying for. dlib scores well on cost but is not accurate enough for small faces in a large hall, so it is kept for prototyping only.

### 5.2 Key reasons

1. **Commercially safe from day one.** MIT and Apache-2.0 licences allow use in a paid college deployment. InsightFace pretrained models and Ultralytics YOLO (AGPL-3.0) do not, without a paid licence. This keeps the "AI licences ₹0" line in the BOM valid.
2. **Same recipe as industry.** The pipeline matches what crowd-recognition vendors use, so the gap is model quality, which can be upgraded stage by stage.
3. **Accuracy is engineered in, not just bought.** Three engineering measures close most of the gap to bigger models:
   - **Tiling**: an 8 MP frame (3840 × 2160) is cut into overlapping tiles, so a back-row face stays at full resolution instead of being shrunk.
   - **Quality gate**: only faces with enough size (target at least 60 pixels between the eyes), sharpness and a near-frontal pose are matched.
   - **Multi-scan voting**: a student is marked present only after several confident matches over the scan window, which removes most single-frame errors.
4. **Fast enough on the edge.** Both models are tiny; with TensorRT FP16 a Jetson Orin can process all six cameras of a hall at a few frames per second each, which is plenty because students are seated and still.
5. **Swappable.** Every model is an ONNX file behind a common interface, so a licensed InsightFace model or a commercial engine can replace one stage without touching the rest.

### 5.3 Licence call-outs (important)

| Item | Licence | What it means for us |
|---|---|---|
| InsightFace **code** | MIT | Free to use |
| InsightFace **pretrained models** (buffalo_l, antelopev2, SCRFD weights, ArcFace R100) | Non-commercial research only | **Must not be used in the college deployment without buying a commercial licence from InsightFace** |
| Ultralytics YOLOv8 / v11 | AGPL-3.0 | Using it would oblige us to publish our full application source, or buy an Ultralytics enterprise licence |
| Public face datasets (MS1M, WebFace, Glint360K, WIDER FACE) | Research / non-commercial | Do not train production models on them; build our own consented test set |
| OpenCV, YuNet, SFace | Apache-2.0 / MIT | Free for commercial use |
| FAISS, ONNX Runtime, ByteTrack, FastAPI | MIT | Free for commercial use |
| NVIDIA JetPack, TensorRT, DeepStream | NVIDIA SDK licence (free) | Free on NVIDIA hardware |
| dlib / face_recognition | Boost / MIT | Free to use; accuracy, not licence, is the limitation |

Licence terms change. Each one must be re-checked against the vendor's current terms before procurement.

---

## 6. Software architecture on the edge unit

See the diagram [`architecture/technology_stack_pipeline.drawio`](../architecture/technology_stack_pipeline.drawio) for the visual version.

### 6.1 Enrolment flow (once per student, at the enrolment station)

1. Student consent recorded (DPDP Act 2023).
2. Capture 5 to 10 images: frontal, slight left/right, slight up/down, with and without spectacles if worn.
3. For each image: YuNet detection → quality gate → passive liveness check → alignment → SFace embedding.
4. Reject and recapture if quality or liveness fails, or if the new template is too similar to an already enrolled different student (duplicate check).
5. Store the embeddings (not only photos) encrypted (AES-256) in the central gallery, keyed by roll number.
6. Synchronise the gallery to all 5 edge units, so any student can be recognised in any hall.

### 6.2 Recognition flow (during each scan window of a lecture)

1. **Capture**: six 8 MP RTSP streams, hardware decoded (GStreamer + NVDEC).
2. **Tile**: each frame split into overlapping tiles sized for the detector.
3. **Detect**: YuNet (TensorRT) finds every face and 5 landmarks; tiles are merged and duplicates removed (non-maximum suppression).
4. **Track**: ByteTrack assigns a track ID to each face so the same person is followed across frames.
5. **Quality gate**: face size, blur (Laplacian variance), head pose from landmarks.
6. **Align and embed**: 112 × 112 aligned crop → SFace (TensorRT) → normalised embedding.
7. **Match**: FAISS search against the roster gallery; accept only above a calibrated threshold and with a clear margin over the second-best match.
8. **Vote**: a track becomes "present: roll number X" after N consistent matches; conflicts are flagged for the lecturer.
9. **Record**: attendance written to SQLite with timestamp, hall, camera and confidence; face crops kept only if policy allows, and for a limited time.
10. **Serve**: the college server pulls records through the FastAPI endpoint (format to be agreed with College IT; see query.pdf).

### 6.3 Code structure (proposed)

```
attendancesystem/
  edge/
    capture/        GStreamer RTSP readers, tiling
    detect/         YuNet wrapper (ONNX / TensorRT), NMS across tiles
    track/          ByteTrack
    recognise/      alignment, SFace wrapper, quality gate
    match/          FAISS gallery, thresholds, voting
    enrol/          enrolment station app, liveness, duplicate check
    store/          SQLite schema, store-and-forward
    api/            FastAPI pull API for the college server
    config/         per-hall camera, threshold and timetable settings
  models/           ONNX files and TensorRT engine build scripts
  tools/            benchmarking and accuracy evaluation scripts
  docker/           Jetson (L4T) and PC images
  docs/             this report and later design documents
  architecture/     draw.io diagrams
```

Each AI stage implements one small interface (for example `Detector.detect(image) -> faces`, `Embedder.embed(face) -> vector`), so the model behind it can be swapped by configuration.

---

## 7. Development approach

The approach is **measure first, then build, then decide**. No schedule is given here; phases follow one another and each ends with a clear exit check.

### Phase 0: Data and benchmark baseline
- With consent, record short clips in one hall from the planned camera positions (front, side, back rows; daylight and artificial light).
- Build a small labelled test set (the people in it enrolled as in Section 6.1).
- Benchmark detection recall per row and recognition accuracy of YuNet + SFace against one or two alternatives (for example dlib for reference, and a commercial SDK evaluation licence).
- **Exit check**: we know, per row, what fraction of faces are found and correctly recognised.

### Phase 1: Prototype pipeline on one edge unit
- Implement capture → tiling → detect → track → quality → embed → match → vote in Python with ONNX Runtime.
- Convert models to TensorRT FP16 on the Jetson and measure frames per second with six streams.
- **Exit check**: all six cameras processed within the scan window on one unit.

### Phase 2: Enrolment station and gallery
- Build the enrolment app with quality checks, liveness, duplicate check and encrypted storage.
- Gallery synchronisation to all edge units.
- **Exit check**: a full class can be enrolled quickly and every template passes quality.

### Phase 3: Accuracy tuning
- Tune camera zoom and focus, tile size, quality thresholds, match threshold and the number of votes on recorded lectures.
- Target figures to be agreed with the college, for example: at least 98% of present students marked, and no more than 0.5% false "present" marks.
- **Decision gate**: if YuNet + SFace cannot meet the targets after tuning, upgrade only the failing stage (detector or embedder) to a licensed InsightFace model or a commercial SDK. This matches the BOM rule "paid engine only if the pilot fails".

### Phase 4: Integration
- FastAPI pull API to the college server's specification; lecturer laptop/mobile app for corrections and opt-outs (RF reader fallback).
- Store-and-forward, logging, health monitoring, Docker packaging, update and rollback.

### Phase 5: Pilot in one hall, then roll-out to all 5
- Run in parallel with the existing attendance method and compare daily.
- Review accuracy, privacy and lecturer feedback; then deploy the same Docker image to the other four halls.

### Engineering practices
- Git repository (this repo) with branches and pull requests; every model file versioned with its licence noted.
- Automated accuracy test: every change is replayed against the recorded test clips and must not lower accuracy.
- Configuration, not code, for per-hall differences.
- Privacy by design: embeddings encrypted at rest, images not kept by default, access logging, deletion on request.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Back-row faces too small | Tiling, motorised zoom set per zone, quality gate, multi-scan voting; upgrade detector if Phase 0 shows low recall |
| Faces hidden (head down, hand, another student) | Several scans per lecture; a student needs to be seen clearly only a few times |
| Look-alikes and twins | Strict threshold with margin, flag for lecturer, RF card fallback |
| Lighting changes | Camera WDR settings, enrol under hall lighting, test day and evening sessions |
| Licence non-compliance | Licence register in the repo; only MIT/Apache/BSD models in production unless a commercial licence is bought |
| Ageing and appearance change | Re-enrol each academic year or on low match confidence |
| Privacy complaint | Consent, encryption, retention limits, opt-out path (RF reader) under DPDP Act 2023 |

---

## 9. Glossary

| Term | Meaning |
|---|---|
| Detection | Finding where faces are in an image |
| Alignment | Rotating and scaling a face so the eyes and mouth are in standard positions |
| Embedding / template | A list of numbers (128 to 512) that describes a face; similar faces give similar numbers |
| 1:N identification | Comparing one face against all N enrolled people |
| Open-set | Some faces in the room may not be enrolled; the system must say "unknown" |
| ONNX | Open file format for AI models, readable by many runtimes |
| TensorRT | NVIDIA's optimiser that makes models run fast on Jetson |
| FAISS | Library for fast similarity search over many embeddings |
| Tracking | Following the same face from frame to frame |
| Liveness | Checking that a real person, not a photo or screen, is in front of the camera |
| NIST FRTE | US government benchmark used by face recognition vendors to compare accuracy |
