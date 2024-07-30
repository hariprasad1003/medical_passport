document.addEventListener("DOMContentLoaded", function() {
    const registerForm = document.getElementById('registerForm');
    const inputs = registerForm.querySelectorAll('input');
    const registerButton = document.getElementById('registerButton');

    registerButton.disabled = true;

    inputs.forEach(input => {
        input.addEventListener('input', validateForm);
    });

    registerForm.addEventListener('submit', function(event) {
        if (!validateForm()) {
            event.preventDefault();
        }
    });
});

function validateForm() {
    const passwordValid = validatePassword();
    const allFieldsFilled = checkRequiredFields();

    const registerButton = document.getElementById('registerButton');
    if (passwordValid && allFieldsFilled) {
        registerButton.disabled = false;
        return true;
    } else {
        registerButton.disabled = true;
        return false;
    }
}

function validatePassword() {
    const password = document.getElementById('password').value;
    const passwordError = document.getElementById('passwordError');
    
    const lengthCheck = password.length >= 8;
    const upperCheck = /[A-Z]/.test(password);
    const lowerCheck = /[a-z]/.test(password);
    const numberCheck = /[0-9]/.test(password);
    const specialCheck = /[!@#$%^&*(),.?":{}|<>]/.test(password);
    
    if (!lengthCheck || !upperCheck || !lowerCheck || !numberCheck || !specialCheck) {
        passwordError.textContent = 'Password must be at least 8 characters long, contain uppercase and lowercase letters, a number, and a special character.';
        return false;
    } else {
        passwordError.textContent = '';
        return true;
    }
}

function checkRequiredFields() {
    const requiredFields = document.querySelectorAll('#registerForm input[required]');
    for (let field of requiredFields) {
        if (!field.value.trim()) {
            return false;
        }
    }
    return true;
}
