let selectedStocks = [];

function showCreateForm() {
    document.getElementById('portfolioForm').style.display = 'block';
    document.getElementById('formTitle').textContent = 'Create Portfolio';
    document.getElementById('portfolioId').value = '';
    resetForm();
}

function editPortfolio(portfolioId) {
    fetch(`/api/v1/portfolios/${portfolioId}`)
        .then(response => response.json())
        .then(portfolio => {
            document.getElementById('portfolioForm').style.display = 'block';
            document.getElementById('formTitle').textContent = 'Edit Portfolio';
            document.getElementById('portfolioId').value = portfolioId;
            document.getElementById('name').value = portfolio.name;
            document.getElementById('currency').value = portfolio.base_currency;
            selectedStocks = portfolio.holdings;
            updateSelectedStocksList();
        });
}

function addStock() {
    const stockSelect = document.getElementById('stockSelect');
    const quantity = document.getElementById('quantity');
    const price = document.getElementById('price');
    const purchaseDate = document.getElementById('purchaseDate');

    selectedStocks.push({
        stock_id: stockSelect.value,
        stock_name: stockSelect.options[stockSelect.selectedIndex].text,
        quantity: parseFloat(quantity.value),
        purchase_price: parseFloat(price.value),
        purchase_date: purchaseDate.value
    });

    updateSelectedStocksList();
    quantity.value = '';
    price.value = '';
    purchaseDate.value = '';
}

function updateSelectedStocksList() {
    const container = document.getElementById('selectedStocks');
    container.innerHTML = selectedStocks.map((stock, index) => `
        <div class="stock-item">
            <span>${stock.stock_name}</span>
            <span>Qty: ${stock.quantity}</span>
            <span>Price: ${stock.purchase_price}</span>
            <button onclick="removeStock(${index})" class="btn-danger">Remove</button>
        </div>
    `).join('');
}

// Add more functions for CRUD operations... 