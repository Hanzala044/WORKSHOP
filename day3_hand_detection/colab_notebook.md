# Day 3 — Hand Detection with OpenCV and MediaPipe (Google Colab)

Copy each numbered section into a separate Google Colab cell and run from top to bottom.

## Cell 1 — Install libraries
```python
!pip -q install opencv-python mediapipe
```

## Cell 2 — Upload a short video
Use a short MP4 video showing hands clearly. Colab will open a file picker.
```python
from google.colab import files
uploaded = files.upload()
video_path = next(iter(uploaded.keys()))
print("Uploaded:", video_path)
```

## Cell 3 — Detect hands and draw landmarks
```python
import cv2
import mediapipe as mp
from pathlib import Path

input_path = video_path
output_path = "hand_detection_output.mp4"

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles

cap = cv2.VideoCapture(input_path)
if not cap.isOpened():
    raise RuntimeError("Could not open uploaded video. Try a standard MP4 file.")

fps = cap.get(cv2.CAP_PROP_FPS)
if not fps or fps <= 0:
    fps = 25.0

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

frame_count = 0
detected_frames = 0

with mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    model_complexity=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
) as hands:
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame_count += 1
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        if result.multi_hand_landmarks:
            detected_frames += 1
            for hand_landmarks in result.multi_hand_landmarks:
                mp_drawing.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_styles.get_default_hand_landmarks_style(),
                    mp_styles.get_default_hand_connections_style()
                )

        writer.write(frame)

cap.release()
writer.release()

print("Frames processed:", frame_count)
print("Frames with a detected hand:", detected_frames)
print("Output:", output_path)
```

## Cell 4 — Preview and download the result
```python
from IPython.display import Video, display
display(Video(output_path, embed=True))
files.download(output_path)
```

## How to explain it
- OpenCV decodes the uploaded video into frames and writes the annotated output video.
- MediaPipe Hands is the pre-trained open-source hand landmark model used here.
- Each detected hand provides 21 landmarks, which are drawn over the frame.
- This starter uses a pre-trained model; it does not train a new model from scratch.
- Results depend on lighting, occlusion, hand size, camera quality, and frame resolution.

## Optional still-image test
Upload an image and run the same `hands.process(rgb)` logic on a single frame. For a real-time local webcam app, run an OpenCV camera loop on your own computer rather than in standard Colab.
