from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
import smtplib
from email.mime.text import MIMEText

from app.database import get_db
from app.config import settings
from app.contact.models import ContactRequest
from app.contact.schemas import ContactRequestCreate, ContactRequestResponse

router = APIRouter(prefix="/contact", tags=["Contact"])

def simulate_send_email(to_email: str, subject: str, body: str):
    logger.info(f"Simulating email dispatch to {to_email}...")
    logger.info(f"Subject: {subject}")
    logger.info(f"Body:\n{body}")
    # In production, SMTP code would run here:
    # try:
    #     msg = MIMEText(body)
    #     msg['Subject'] = subject
    #     msg['From'] = settings.EMAIL_FROM
    #     msg['To'] = to_email
    #     with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
    #         server.starttls()
    #         server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
    #         server.sendmail(settings.EMAIL_FROM, [to_email], msg.as_string())
    # except Exception as e:
    #     logger.error(f"Failed to send email: {e}")

@router.post("/", response_model=ContactRequestResponse, status_code=status.HTTP_201_CREATED)
async def submit_contact_form(
    form_in: ContactRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    ip_address = request.client.host if request.client else None
    
    # Store request details in database
    db_request = ContactRequest(
        first_name=form_in.first_name,
        last_name=form_in.last_name,
        email=form_in.email,
        company=form_in.company,
        client_type=form_in.client_type,
        message=form_in.message,
        ip_address=ip_address
    )
    db.add(db_request)
    await db.commit()
    await db.refresh(db_request)

    # 1. Send notification email to administrator
    admin_body = f"""
    New NobleVest contact request:
    Name: {form_in.first_name} {form_in.last_name}
    Email: {form_in.email}
    Company: {form_in.company or 'N/A'}
    Client Type: {form_in.client_type or 'N/A'}
    Message:
    {form_in.message or ''}
    
    IP Address: {ip_address}
    """
    simulate_send_email(
        to_email=settings.ADMIN_EMAIL,
        subject=f"New Contact Request - {form_in.first_name} {form_in.last_name}",
        body=admin_body
    )

    # 2. Send confirmation email to sender
    sender_body = f"""
    Dear {form_in.first_name},
    
    Thank you for contacting NobleVest. We have received your inquiry and our institutional sales team will get back to you shortly.
    
    Summary of your submission:
    Company: {form_in.company or 'N/A'}
    Client Type: {form_in.client_type or 'N/A'}
    
    Best regards,
    The NobleVest Team
    """
    simulate_send_email(
        to_email=form_in.email,
        subject="NobleVest - Inquiry Confirmation",
        body=sender_body
    )

    return db_request
