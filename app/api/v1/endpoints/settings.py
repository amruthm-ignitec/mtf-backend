from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any
import logging
from app.database.database import get_db
from app.models.setting import Setting, SettingType
from app.models.user import User, UserRole
from app.schemas.setting import SettingResponse, SettingsResponse, SettingsUpdate
from app.api.v1.endpoints.auth import get_current_user
from app.core.security import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", response_model=SettingsResponse)
async def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all system settings (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    settings = db.query(Setting).all()
    settings_dict = {}
    
    for setting in settings:
        value = setting.value
        if setting.is_encrypted and value:
            try:
                value = decrypt_value(value)
            except Exception as e:
                logger.warning(f"Failed to decrypt setting {setting.key}: {e}")
                value = None
        
        settings_dict[setting.key.value] = value
    
    return SettingsResponse(**settings_dict)

@router.put("/", response_model=SettingsResponse)
async def update_settings(
    settings_update: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update system settings (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    # Define which settings should be encrypted
    encrypted_keys = {
        'openai_api_key', 'azure_api_key', 'google_api_key', 'anthropic_api_key'
    }
    
    update_data = settings_update.dict(exclude_unset=True)
    
    for key, value in update_data.items():
        if value is None:
            continue
            
        setting_type = SettingType(key)
        existing_setting = db.query(Setting).filter(Setting.key == setting_type).first()
        
        # Determine if this setting should be encrypted
        is_encrypted = key in encrypted_keys
        
        # Encrypt sensitive values
        if is_encrypted and value:
            try:
                encrypted_value = encrypt_value(value)
            except Exception as e:
                logger.error(f"Failed to encrypt setting {key}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to encrypt setting {key}"
                )
        else:
            encrypted_value = value
        
        if existing_setting:
            # Update existing setting
            existing_setting.value = encrypted_value
            existing_setting.is_encrypted = is_encrypted
            db.add(existing_setting)
        else:
            # Create new setting
            new_setting = Setting(
                key=setting_type,
                value=encrypted_value,
                is_encrypted=is_encrypted,
                description=f"System setting for {key}"
            )
            db.add(new_setting)
    
    db.commit()
    
    logger.info(f"Settings updated by admin: {current_user.email}")
    
    # Return updated settings
    settings = db.query(Setting).all()
    settings_dict = {}
    
    for setting in settings:
        value = setting.value
        if setting.is_encrypted and value:
            try:
                value = decrypt_value(value)
            except Exception as e:
                logger.warning(f"Failed to decrypt setting {setting.key}: {e}")
                value = None
        
        settings_dict[setting.key.value] = value
    
    return SettingsResponse(**settings_dict)

@router.get("/{setting_key}", response_model=SettingResponse)
async def get_setting(
    setting_key: SettingType,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific setting (Admin only)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    setting = db.query(Setting).filter(Setting.key == setting_key).first()
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Setting not found"
        )
    
    # Decrypt if needed
    if setting.is_encrypted and setting.value:
        try:
            setting.value = decrypt_value(setting.value)
        except Exception as e:
            logger.warning(f"Failed to decrypt setting {setting_key}: {e}")
            setting.value = None
    
    return setting
