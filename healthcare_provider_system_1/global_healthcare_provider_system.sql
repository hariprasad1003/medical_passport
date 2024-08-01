CREATE DATABASE global_healthcare_provider_system;
USE global_healthcare_provider_system;

DROP TABLE IF EXISTS healthcare_provider;

CREATE TABLE healthcare_provider (
    healthcare_provider_id INT PRIMARY KEY,
    healthcare_provider_name VARCHAR(100) NOT NULL,
    healthcare_provider_domain VARCHAR(100) NOT NULL,
    house_number_post_box_number VARCHAR(50),
    post_code VARCHAR(10),
    country VARCHAR(50)
);