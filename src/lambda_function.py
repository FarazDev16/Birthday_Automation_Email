import boto3, json, pandas as pd
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io, random, os, traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
ses = boto3.client("ses")


def lambda_handler(event, context):
    try:
        print("Lambda started.")

        bucket = os.environ.get("CONFIG_BUCKET")
        config_key = os.environ.get("CONFIG_KEY")
        messages_key = os.environ.get("MESSAGES_KEY")

        if not all([bucket, config_key, messages_key]):
            raise ValueError("One or more required environment variables are missing.")

        # Helper to safely get S3 object
        def get_s3_object(bucket, key):
            print(f"Fetching S3 object -> Bucket: {bucket}, Key: {key}")
            try:
                return s3.get_object(Bucket=bucket, Key=key)
            except ClientError as e:
                if e.response['Error']['Code'] == "NoSuchKey":
                    raise FileNotFoundError(f"S3 key not found: {key}")
                else:
                    raise

        # Load config
        config_obj = get_s3_object(bucket, config_key)
        config = json.loads(config_obj["Body"].read().decode("utf-8"))
        print("Config loaded from S3:", config_key)

        # Load month-wise messages
        messages_obj = get_s3_object(bucket, messages_key)
        monthly_messages = json.loads(messages_obj["Body"].read().decode("utf-8"))
        print("Monthly messages loaded:", messages_key)

        current_month = datetime.now().strftime("%B")
        print("Current month:", current_month)

        # Load Excel file
        excel_file_key = config.get("excel_file")
        if not excel_file_key:
            raise ValueError("Excel file key missing in config.")
        excel_obj = get_s3_object(bucket, excel_file_key)
        df = pd.read_excel(io.BytesIO(excel_obj["Body"].read()), engine="openpyxl")
        print("Excel file loaded:", excel_file_key)

        names = df[current_month].dropna().tolist() if current_month in df.columns else []
        print("Names found:", names)

        if not names:
            print("No birthdays this month.")
            return {"statusCode": 200, "body": "No birthdays this month"}

        # Load template image
        templates = config.get("templates", [])
        if not templates:
            raise ValueError("No templates provided in config.")
        template_key = random.choice(templates)
        template_obj = get_s3_object(bucket, template_key)
        img = Image.open(io.BytesIO(template_obj["Body"].read())).convert("RGBA")
        print("Template loaded:", template_key)

        # Resize template if needed
        max_width, max_height = 1200, 800
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height))
        print("Template resized if necessary.")

        # Load bubble image (random selection)
        bubble_images = config.get("bubble_images", [])
        if not bubble_images:
            raise ValueError("No bubble images provided in config.")
        bubble_key = random.choice(bubble_images)
        bubble_obj = get_s3_object(bucket, bubble_key)
        img = add_bubble_with_names(img, bubble_obj["Body"].read(), names, size_ratio=0.4)
        print(f"Bubble chosen: {bubble_key}")

        # Save final image to memory
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="PNG")
        output_buffer.seek(0)
        print("Image saved to memory buffer.")

        # Build email
        raw_message = build_email(
            sender=config["sender_email"],
            recipients=config["recipients"],
            image_buffer=output_buffer,
            monthly_messages=monthly_messages
        )
        print("Email built successfully.")

        # Send email via SES
        response = ses.send_raw_email(
            Source=config["sender_email"],
            Destinations=config["recipients"],
            RawMessage={"Data": raw_message}
        )
        print("Email sent! SES MessageId:", response.get("MessageId"))

        return {"statusCode": 200, "body": "Email sent successfully!"}

    except Exception as e:
        print("Lambda execution failed:", e)
        traceback.print_exc()
        return {"statusCode": 500, "body": f"Lambda failed: {e}"}


# ---------------- Helper Functions ----------------

def build_email(sender, recipients, image_buffer, monthly_messages):
    current_month = datetime.now().strftime("%B")
    message_info = monthly_messages.get(current_month, {"subject": "Birthday!", "body": ""})

    msg = MIMEMultipart()
    msg["Subject"] = message_info.get("subject", "Birthday!")
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(message_info.get("body", ""), "plain"))

    image_buffer.seek(0)
    img = MIMEImage(image_buffer.read(), _subtype="png")
    img.add_header("Content-Disposition", "attachment", filename="birthday_card.png")
    msg.attach(img)

    return msg.as_string()


def add_bubble_with_names(img, bubble_bytes, names, size_ratio=0.5):
    base_w, base_h = img.size
    bubble_img = Image.open(io.BytesIO(bubble_bytes)).convert("RGBA")

    font_path = "arialbi.ttf"
    try:
        font_size = 50  # Start bigger
        font = ImageFont.truetype(font_path, font_size)
    except:
        font_size = 30
        font = ImageFont.load_default()

    text = "\n".join(names)

    # Dynamically adjust bubble size OR reduce font size
    temp_draw = ImageDraw.Draw(img)
    padding = 60

    while True:
        # Get text dimensions for current font size
        text_bbox = temp_draw.multiline_textbbox((0, 0), text, font=font, spacing=8)
        text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]

        # Required bubble dimensions
        required_w = text_w + padding
        required_h = text_h + padding

        # Initial bubble size from ratio
        new_width = max(int(base_w * size_ratio), required_w)
        aspect_ratio = bubble_img.height / bubble_img.width
        new_height = max(int(new_width * aspect_ratio), required_h)

        # If bubble fits inside base image, break loop; else reduce font size and retry
        if new_width <= base_w and new_height <= base_h:
            break
        else:
            font_size -= 2
            if font_size < 15:  # Avoid too small fonts
                font_size = 15
                break
            font = ImageFont.truetype(font_path, font_size)

    # Resize bubble and center on base image
    bubble_img = bubble_img.resize((new_width, new_height), Image.LANCZOS)
    bubble_x = (base_w - new_width) // 2
    bubble_y = (base_h - new_height) // 2
    img.paste(bubble_img, (bubble_x, bubble_y), bubble_img)

    # Draw text centered in bubble
    text_bbox = temp_draw.multiline_textbbox((0, 0), text, font=font, spacing=8)
    text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
    text_x = bubble_x + (new_width - text_w) // 2
    text_y = bubble_y + (new_height - text_h) // 2
    top_padding = 40 
    text_y = bubble_y + top_padding 

    draw = ImageDraw.Draw(img)
    draw.multiline_text((text_x, text_y), text, font=font, fill=(0, 0, 0), spacing=8)

    return img

