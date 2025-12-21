import torch
from PIL import Image
import supervision as sv
from transformers import AutoProcessor, AutoModelForImageTextToText

MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
# MODEL_ID = "Qwen/Qwen3-VL-4B-Instruct"
# MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"

# Automatically select the best available device
# Note: MPS (Apple Silicon GPU) often has compatibility issues with vision-language models
# For stability, we use CPU on macOS
if torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"
    # Uncomment the following to try MPS (may not work with all models)
    # if torch.backends.mps.is_available():
    #     device = "mps"

print(f"Using device: {device}")

processor = AutoProcessor.from_pretrained(MODEL_ID)
model = AutoModelForImageTextToText.from_pretrained(MODEL_ID).to(device)

COLOR = sv.ColorPalette.from_hex([
    "#ffff00", "#ff9b00", "#ff66ff", "#3399ff", "#ff66b2", "#ff8080",
    "#b266ff", "#9999ff", "#66ffff", "#33ff99", "#66ff66", "#99ff00"
])

def annotate_image(image: Image, detections: sv.Detections, smart_position = True) -> Image:
    text_scale = sv.calculate_optimal_text_scale(resolution_wh=image.size)
    thickness = sv.calculate_optimal_line_thickness(resolution_wh=image.size)

    color_by_class = detections.class_id is not None
    box_annotator = sv.BoxAnnotator(
        color=COLOR,
        color_lookup=sv.ColorLookup.CLASS if color_by_class else sv.ColorLookup.INDEX,
        thickness=thickness
    )
    label_annotator = sv.LabelAnnotator(
        color=COLOR,
        color_lookup=sv.ColorLookup.CLASS if color_by_class else sv.ColorLookup.INDEX,
        text_color=sv.Color.BLACK,
        text_scale=text_scale,
        text_thickness=thickness - 1,
        smart_position=smart_position
    )

    annotated_image = image.copy()
    annotated_image = box_annotator.annotate(annotated_image, detections)
    return label_annotator.annotate(annotated_image, detections)
def qwen_detect(image: Image, target: str, max_new_tokens: int = 1024):

    prompt = (
        f"Outline the position of {target} and output all the coordinates in JSON format."
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    )

    # Move inputs to the same device as the model
    inputs = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in inputs.items()}

    with torch.inference_mode():
        gen = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
        )

    trimmed = [g[len(i):] for i, g in zip(inputs.input_ids, gen)]
    text = processor.batch_decode(trimmed, skip_special_tokens=True)[0]
    return text

IMAGE = "./fire.png"

TARGET = "Fire"

image = Image.open(IMAGE).convert("RGB")
response = qwen_detect(image, TARGET)

print(response)

detections = sv.Detections.from_vlm(
    vlm=sv.VLM.QWEN_3_VL,
    result=response,
    resolution_wh=image.size
)

annotated_image = image.copy()
annotated_image = annotate_image(image=annotated_image, detections=detections)
annotated_image.thumbnail((800, 800))
annotated_image