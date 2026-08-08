CREATE DATABASE IF NOT EXISTS travellens;
USE travellens;

CREATE TABLE IF NOT EXISTS hotels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    website VARCHAR(50) NOT NULL,
    hotel_url TEXT,
    image_url TEXT,
    currency VARCHAR(10),
    rating DECIMAL(3,1),
    reviews INT,
    original_price DECIMAL(10,2),
    discount_percentage DECIMAL(5,2),
    price DECIMAL(10,2),
    is_tax_included BOOLEAN DEFAULT TRUE,
    tax_amount DECIMAL(10,2),
    amenities TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

SHOW TABLES;
DESCRIBE hotels;

ALTER TABLE hotels
    ADD COLUMN city VARCHAR(100),
    ADD COLUMN check_in DATE,
    ADD COLUMN check_out DATE,
    ADD COLUMN adults INT;
