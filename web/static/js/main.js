// Form submission for creating portfolio
document.addEventListener('DOMContentLoaded', function() {
    const portfolioForm = document.getElementById('portfolioForm');
    if (portfolioForm) {
        portfolioForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = {
                name: document.getElementById('name').value,
                base_currency: document.getElementById('currency').value,
                holdings: [] // We'll add holdings functionality later
            };

            try {
                const response = await fetch('/api/v1/portfolios/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(formData)
                });

                if (response.ok) {
                    window.location.href = '/'; // Redirect to dashboard
                } else {
                    alert('Error creating portfolio');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Error creating portfolio');
            }
        });
    }
});

// Navigation functions
function createPortfolio() {
    window.location.href = '/portfolios/new';
}

function viewPortfolios() {
    window.location.href = '/portfolios';
} 