"""
Image processing utilities for POS system
"""
import os
import uuid
import imghdr
from flask import current_app
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps


def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def validate_image(file):
    """Validate uploaded image file"""
    if not file or file.filename == '':
        return False, 'Файл не выбран'
    
    if not allowed_file(file.filename):
        return False, 'Недопустимый тип файла. Разрешены: PNG, JPG, JPEG, GIF'
    
    # Check file content type
    file.seek(0)
    header = file.read(512)
    file.seek(0)
    
    format = imghdr.what(None, header)
    if not format or format not in ['jpeg', 'png', 'gif']:
        return False, 'Файл не является изображением'
    
    return True, 'OK'


def generate_unique_filename(original_filename):
    """Generate unique filename for uploaded image (normalized to .jpg)"""
    unique_id = str(uuid.uuid4())[:8]
    secure_name = secure_filename(original_filename.rsplit('.', 1)[0])
    return f"{unique_id}_{secure_name}.jpg"


def process_product_image(file, filename):
    """Process uploaded product image - resize and create thumbnail (all saved as JPEG)"""
    try:
        # Open and process the image
        image = Image.open(file)
        
        # Convert RGBA to RGB if necessary
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Auto-orient the image
        image = ImageOps.exif_transpose(image)
        
        # Resize main image if it's too large
        max_size = (current_app.config['MAX_IMAGE_WIDTH'], current_app.config['MAX_IMAGE_HEIGHT'])
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save main image as JPEG (filename already has .jpg extension)
        main_image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products', filename)
        os.makedirs(os.path.dirname(main_image_path), exist_ok=True)
        image.save(main_image_path, 'JPEG', quality=85, optimize=True)
        
        # Create and save thumbnail as JPEG
        thumbnail = image.copy()
        thumbnail.thumbnail(current_app.config['THUMBNAIL_SIZE'], Image.Resampling.LANCZOS)
        
        thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products', 'thumbnails', filename)
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        thumbnail.save(thumbnail_path, 'JPEG', quality=80, optimize=True)
        
        return True, filename
        
    except Exception as e:
        return False, f'Ошибка обработки изображения: {str(e)}'


def delete_product_image(filename):
    """Delete product image and thumbnail"""
    if not filename:
        return
    
    main_image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products', filename)
    thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products', 'thumbnails', filename)
    
    # Delete main image
    if os.path.exists(main_image_path):
        try:
            os.remove(main_image_path)
        except OSError:
            pass
    
    # Delete thumbnail
    if os.path.exists(thumbnail_path):
        try:
            os.remove(thumbnail_path)
        except OSError:
            pass