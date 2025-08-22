# Birthday Automation Email 🎂

This project automatically sends a monthly birthday email with a dynamically generated birthday card using AWS Lambda, S3, SES, and EventBridge.

---

## Features
- Reads employee birthdays from an Excel file stored in S3.
- Dynamically selects a random birthday card template from S3.
- Draws employee names on the card using Pillow (PIL).
- Sends an email with SES to configured recipients.
- Runs automatically on a schedule using AWS EventBridge.

---

## Architecture
1. S3 Bucket
   - Stores the Excel file (`Employees_Birthday_List.xlsx`) with monthly birthday data.
   - Stores birthday card templates (PNG/JPG).
2. Lambda Function
   - Reads Excel and templates from S3.
   - Generates a customized birthday card image.
   - Sends email via SES.
3. SES (Simple Email Service)
   - Sends the email to your recipients.
4. EventBridge Rule
   - Triggers the Lambda function on a schedule (e.g., 1st of every month at 9 AM).

---

## Excel File Format
Ensure your Excel file in S3 has month names as columns:
| January  | February | March    | ... |
|----------|----------|----------|-----|
| John     | Martin   | Lisa     |     |
| Sarah    | George   |          |     |

---

## Setup Steps

### 1. Create S3 Bucket
Upload:
- `Employees_Birthday_List/Employees_Birthday_List.xlsx` (with birthdays data)
- `Templates/template1.png`, `templates/template2.png`

### 2. Configure SES
- Verify `sender_email` and recipient emails in SES.
- (Optional) Move SES out of sandbox mode for production.

### 3. Deploy Lambda
1. Create a Lambda function (Python 3.9+).
2. Add environment variables:
