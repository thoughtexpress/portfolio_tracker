// Stock search and selection handling
let selectedStock = null;
const stockSearch = document.getElementById('stockSearch');
const searchResults = document.getElementById('stockSearchResults');

const debounce = (func, wait) => {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

const searchStocks = debounce(async (query) => {
    if (query.length < 2) {
        searchResults.innerHTML = '';
        return;
    }

    try {
        const response = await fetch(`/api/stocks/search?query=${encodeURIComponent(query)}`);
        const stocks = await response.json();
        
        searchResults.innerHTML = stocks.map(stock => `
            <div class="search-result-item" onclick="selectStock('${stock.id}', '${stock.symbol}', '${stock.name}')">
                <span class="stock-symbol">${stock.symbol}</span>
                <span class="stock-name">${stock.name}</span>
            </div>
        `).join('');
    } catch (error) {
        console.error('Stock search failed:', error);
    }
}, 300);

function selectStock(stockId, symbol, name) {
    selectedStock = { id: stockId, symbol, name };
    stockSearch.value = `${symbol} - ${name}`;
    searchResults.innerHTML = '';
}

// Charge calculation handling
async function updateChargeStructure() {
    const brokerName = document.getElementById('broker').value;
    if (!brokerName) return;

    try {
        const response = await fetch(`/api/brokers/${brokerName}/charges`);
        const chargeStructure = await response.json();
        calculateCharges(chargeStructure);
    } catch (error) {
        console.error('Failed to fetch charge structure:', error);
    }
}

function calculateCharges(chargeStructure = null) {
    const quantity = parseFloat(document.getElementById('quantity').value) || 0;
    const price = parseFloat(document.getElementById('price').value) || 0;
    const transactionType = document.getElementById('transactionType').value;
    
    const totalValue = quantity * price;
    document.getElementById('totalValue').value = totalValue.toFixed(2);

    if (chargeStructure) {
        // Calculate charges based on broker's structure
        const brokerage = totalValue * chargeStructure.brokerage_percentage;
        const gst = brokerage * chargeStructure.gst_percentage;
        const stt = totalValue * chargeStructure.stt_percentage;
        const stampDuty = totalValue * chargeStructure.stamp_duty_percentage;
        const exchangeCharges = totalValue * chargeStructure.exchange_charges_percentage;
        const sebiCharges = totalValue * chargeStructure.sebi_charges_percentage;

        document.getElementById('brokerage').value = brokerage.toFixed(2);
        document.getElementById('gst').value = gst.toFixed(2);
        document.getElementById('stt').value = stt.toFixed(2);
        document.getElementById('stampDuty').value = stampDuty.toFixed(2);
        document.getElementById('exchangeCharges').value = exchangeCharges.toFixed(2);
        document.getElementById('sebiCharges').value = sebiCharges.toFixed(2);

        const totalCharges = brokerage + gst + stt + stampDuty + exchangeCharges + sebiCharges;
        document.getElementById('totalCharges').value = totalCharges.toFixed(2);

        const netAmount = transactionType === 'BUY' ? totalValue + totalCharges : totalValue - totalCharges;
        document.getElementById('netAmount').value = netAmount.toFixed(2);
    }
}

// Form submission
async function saveTransaction() {
    if (!validateForm()) return;

    const formData = {
        portfolio_id: document.getElementById('portfolioId').value,
        stock_id: selectedStock.id,
        transaction_type: document.getElementById('transactionType').value,
        quantity: parseFloat(document.getElementById('quantity').value),
        price: parseFloat(document.getElementById('price').value),
        date: document.getElementById('transactionDate').value,
        broker: {
            name: document.getElementById('broker').value,
            transaction_id: document.getElementById('brokerTransactionId').value
        },
        charges: {
            brokerage: parseFloat(document.getElementById('brokerage').value),
            gst: parseFloat(document.getElementById('gst').value),
            stt: parseFloat(document.getElementById('stt').value),
            stamp_duty: parseFloat(document.getElementById('stampDuty').value),
            exchange_charges: parseFloat(document.getElementById('exchangeCharges').value),
            sebi_charges: parseFloat(document.getElementById('sebiCharges').value)
        },
        notes: document.getElementById('notes').value
    };

    try {
        const response = await fetch('/transactions/new', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });

        const result = await response.json();

        if (response.ok) {
            alert('Transaction saved successfully!');
            window.location.href = '/transactions';
        } else {
            throw new Error(result.error || 'Failed to save transaction');
        }
    } catch (error) {
        console.error('Error saving transaction:', error);
        alert('Error saving transaction: ' + error.message);
    }
}

function validateForm() {
    // Add your validation logic here
    return true;
}

// Event listeners
stockSearch.addEventListener('input', (e) => searchStocks(e.target.value));
document.getElementById('quantity').addEventListener('input', calculateCharges);
document.getElementById('price').addEventListener('input', calculateCharges);
document.getElementById('transactionType').addEventListener('change', calculateCharges); 