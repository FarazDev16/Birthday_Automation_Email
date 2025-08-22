import boto3, json, pandas as pd
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io, random, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

s3 = boto3.client("s3")
ses = boto3.client("ses")

def lambda_handler(event, context):
    print("🔹 Lambda invoked! Event:", event)
    try:
        print("🔹 Lambda started")

        bucket = os.environ.get("CONFIG_BUCKET")
        config_key = os.environ.get("CONFIG_KEY")
        print("Bucket:", bucket, "Config Key:", config_key)

        # Load config from S3
        try:
            config_obj = s3.get_object(Bucket=bucket, Key=config_key)
            config = json.loads(config_obj["Body"].read().decode("utf-8"))
            print("✅ Config loaded:", config)
        except s3.exceptions.NoSuchKey:
            print("❌ Config file not found:", config_key)
            return {"statusCode": 500, "body": f"Config file '{config_key}' not found"}

        current_month = datetime.now().strftime("%B")
        print("Current month:", current_month)

        # Load Excel file
        try:
            excel_obj = s3.get_object(Bucket=bucket, Key=config["excel_file"])
            excel_bytes = io.BytesIO(excel_obj["Body"].read())
            df = pd.read_excel(excel_bytes, engine="openpyxl")
            print("✅ Excel loaded. Columns:", df.columns.tolist())
        except s3.exceptions.NoSuchKey:
            print("❌ Excel file not found:", config["excel_file"])
            return {"statusCode": 500, "body": f"Excel file '{config['excel_file']}' not found"}
        except Exception as e:
            print("❌ Error reading Excel:", str(e))
            return {"statusCode": 500, "body": f"Error reading Excel: {e}"}

        names = df[current_month].dropna().tolist() if current_month in df.columns else []
        print("Names found:", names)
        if not names:
            print("ℹ️ No birthdays this month")
            return {"statusCode": 200, "body": "No birthdays this month"}

        # Load templates
        templates = config.get("templates", [])
        print("Templates available:", templates)
        if not templates:
            print("❌ No templates provided in config")
            return {"statusCode": 500, "body": "No templates provided in config"}

        template_key = random.choice(templates)
        print("Template selected:", template_key)
        try:
            template_obj = s3.get_object(Bucket=bucket, Key=template_key)
            img = Image.open(io.BytesIO(template_obj["Body"].read()))
            print("✅ Template image loaded")
        except s3.exceptions.NoSuchKey:
            print("❌ Template file not found:", template_key)
            return {"statusCode": 500, "body": f"Template file '{template_key}' not found"}
        except Exception as e:
            print("❌ Error opening template:", str(e))
            return {"statusCode": 500, "body": f"Error opening template: {e}"}

        # Resize image if too large
        max_width, max_height = 1200, 800
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height))
            print("ℹ️ Template resized to fit")

        draw = ImageDraw.Draw(img)

        # Draw names
        try:
            font_size = 50
            font_path = "arialbi.ttf"
            font = ImageFont.truetype(font_path, font_size)
        except:
            font = ImageFont.load_default()
        spacing_value = 5
        text = "\n".join(names)
        W, H = img.size

        # Auto-adjust font size to fit
        while True:
            bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing_value)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if text_h < H * 0.8 or font_size <= 15:
                break
            font_size -= 2
            try:
                font = ImageFont.truetype(font_path, font_size)
            except:
                font = ImageFont.load_default()
                break

        x, y = (W - text_w) / 2, (H - text_h) / 2
        draw.multiline_text((x, y), text, font=font, fill="black", spacing=spacing_value, align="center")
        print("✅ Names drawn on template")

        # Save image to memory
        output_buffer = io.BytesIO()
        img.save(output_buffer, format="PNG")
        output_buffer.seek(0)
        print("✅ Image saved to buffer")

        # Send email via SES
        try:
            output_buffer.seek(0)
            raw_message = build_email(config["sender_email"], config["recipients"], output_buffer)
            response = ses.send_raw_email(
                Source=config["sender_email"],
                Destinations=config["recipients"],
                RawMessage={"Data": raw_message}
            )
            print("✅ Email sent! SES MessageId:", response.get("MessageId"))
        except Exception as e:
            print("❌ Email sending failed:", str(e))
            return {"statusCode": 500, "body": f"Email sending failed: {e}"}

        return {"statusCode": 200, "body": "Email sent successfully!"}

    except Exception as e:
        print("❌ Lambda failed:", str(e))
        return {"statusCode": 500, "body": f"Lambda failed: {e}"}


def build_email(sender, recipients, image_buffer):
    msg = MIMEMultipart()
    msg["Subject"] = f"🎂 Happy Birthday - {datetime.now().strftime('%B %Y')}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText("Wishing a fantastic birthday to our stars of the month! 🌟🎉", "plain"))

    image_buffer.seek(0)
    img = MIMEImage(image_buffer.read(), _subtype="png")
    img.add_header("Content-Disposition", "attachment", filename="birthday_card.png")
    msg.attach(img)

    return msg.as_string()
