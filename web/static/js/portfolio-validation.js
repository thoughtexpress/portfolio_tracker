const validationRules = {
    portfolioName: {
        required: true,
        maxLength: 100,
        pattern: /^[A-Za-z0-9\s]+$/,
        message: "Name must be 1-100 characters, letters and numbers only"
    },
    quantity: {
        required: true,
        min: 0.01,
        message: "Quantity must be greater than 0"
    },
    purchasePrice: {
        required: true,
        min: 0.01,
        message: "Price must be greater than 0"
    },
    purchaseDate: {
        required: true,
        maxDate: new Date(),
        message: "Date cannot be in the future"
    }
};

function validateField(field, value) {
    const rules = validationRules[field];
    if (!rules) return true;

    if (rules.required && !value) {
        return rules.message;
    }

    if (rules.maxLength && value.length > rules.maxLength) {
        return rules.message;
    }

    if (rules.pattern && !rules.pattern.test(value)) {
        return rules.message;
    }

    if (rules.min && parseFloat(value) < rules.min) {
        return rules.message;
    }

    if (rules.maxDate && new Date(value) > rules.maxDate) {
        return rules.message;
    }

    return null;
}

function showError(elementId, message) {
    const element = document.getElementById(elementId);
    const formGroup = element.closest('.form-group');
    formGroup.classList.add('error');
    
    let errorDiv = formGroup.querySelector('.validation-error');
    if (!errorDiv) {
        errorDiv = document.createElement('div');
        errorDiv.className = 'validation-error';
        formGroup.appendChild(errorDiv);
    }
    errorDiv.textContent = message;
}

function clearError(elementId) {
    const element = document.getElementById(elementId);
    const formGroup = element.closest('.form-group');
    formGroup.classList.remove('error');
    const errorDiv = formGroup.querySelector('.validation-error');
    if (errorDiv) {
        errorDiv.remove();
    }
} 