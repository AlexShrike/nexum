const { html, Component, render, useState, useEffect } = window.htmPreact;

// Utility functions
const formatDate = (dateString) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleString();
};

const formatCurrency = (amount, currency = 'USD') => {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency
    }).format(amount || 0);
};

const api = {
    async get(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    },

    async post(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }
};

// Navigation component
function Sidebar({ currentPage, onPageChange }) {
    const corePages = [
        { id: 'overview', label: 'Overview', icon: 'chart-line' },
        { id: 'customers', label: 'Customers', icon: 'users' },
        { id: 'accounts', label: 'Accounts', icon: 'credit-card' },
        { id: 'transactions', label: 'Transactions', icon: 'exchange-alt' },
        { id: 'loans', label: 'Loans', icon: 'money-bill-wave' },
        { id: 'credit-lines', label: 'Credit Lines', icon: 'credit-card' },
        { id: 'collections', label: 'Collections', icon: 'exclamation-triangle' },
        { id: 'products', label: 'Products', icon: 'box' }
    ];

    const adminPages = [
        { id: 'users', label: 'Users & RBAC', icon: 'user-shield' },
        { id: 'audit', label: 'Audit Trail', icon: 'clipboard-list' },
        { id: 'workflows', label: 'Workflows', icon: 'project-diagram' },
        { id: 'notifications', label: 'Notifications', icon: 'bell' },
        { id: 'compliance', label: 'Compliance', icon: 'balance-scale' },
        { id: 'settings', label: 'Settings', icon: 'cog' }
    ];

    return html`
        <div class="sidebar">
            <div class="sidebar-header">
                <h1 class="sidebar-title">Nexum Banking</h1>
                <p class="sidebar-subtitle">Core Banking Platform</p>
            </div>
            
            <nav class="nav-menu">
                ${corePages.map(item => html`
                    <li key=${item.id} class="nav-item">
                        <a
                            class="nav-link ${currentPage === item.id ? 'active' : ''}"
                            href="#"
                            onClick=${(e) => { e.preventDefault(); onPageChange(item.id); }}
                        >
                            ${item.label}
                        </a>
                    </li>
                `)}
                
                <li class="nav-item" style="margin: 1rem 0; padding: 0 1rem;">
                    <div style="height: 1px; background: rgba(255, 255, 255, 0.1);"></div>
                </li>
                
                ${adminPages.map(item => html`
                    <li key=${item.id} class="nav-item">
                        <a
                            class="nav-link ${currentPage === item.id ? 'active' : ''}"
                            href="#"
                            onClick=${(e) => { e.preventDefault(); onPageChange(item.id); }}
                        >
                            ${item.label}
                        </a>
                    </li>
                `)}
            </nav>
        </div>
    `;
}

// Main content wrapper
function MainContent({ children }) {
    return html`
        <div class="main-content">
            <div class="content-body">
                ${children}
            </div>
        </div>
    `;
}

// Overview Page
function OverviewPage() {
    const [overview, setOverview] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadOverview();
    }, []);

    const loadOverview = async () => {
        try {
            setLoading(true);
            const data = await api.get('/api/overview');
            setOverview(data);
        } catch (error) {
            console.error('Failed to load overview:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return html`<div class="loading">Loading overview...</div>`;
    if (!overview) return html`<div class="error">Failed to load overview data</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Overview</h1>
                <p class="page-subtitle">Core banking system dashboard</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Total Accounts</h3>
                    </div>
                    <div class="stat-value">${overview.accounts.total}</div>
                    <div class="stat-change">
                        ${overview.accounts.by_type.savings} Savings, ${overview.accounts.by_type.checking} Checking
                    </div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Total Deposits</h3>
                    </div>
                    <div class="stat-value">${formatCurrency(overview.balances.total_deposits)}</div>
                    <div class="stat-change">Available customer funds</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Outstanding Loans</h3>
                    </div>
                    <div class="stat-value">${formatCurrency(overview.balances.total_loans)}</div>
                    <div class="stat-change">${overview.accounts.by_type.loans} active loans</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Credit Utilized</h3>
                    </div>
                    <div class="stat-value">${formatCurrency(overview.balances.total_credit_used)}</div>
                    <div class="stat-change">${overview.accounts.by_type.credit_lines} credit lines</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Transactions (30d)</h3>
                    </div>
                    <div class="stat-value">${overview.transactions.count_30d}</div>
                    <div class="stat-change">Volume: ${formatCurrency(overview.transactions.volume_30d)}</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Collection Cases</h3>
                    </div>
                    <div class="stat-value">${overview.collections.total_cases}</div>
                    <div class="stat-change amount-negative">Overdue: ${formatCurrency(overview.collections.total_overdue)}</div>
                </div>
            </div>
        </div>
    `;
}

// Customers Page
function CustomersPage() {
    const [customers, setCustomers] = useState([]);
    const [selectedCustomer, setSelectedCustomer] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadCustomers();
    }, []);

    const loadCustomers = async () => {
        try {
            setLoading(true);
            const data = await api.get('/api/customers');
            setCustomers(data);
        } catch (error) {
            console.error('Failed to load customers:', error);
        } finally {
            setLoading(false);
        }
    };

    const viewCustomerDetail = async (customerId) => {
        try {
            const customerDetail = await api.get(`/api/customers/${customerId}`);
            setSelectedCustomer(customerDetail);
        } catch (error) {
            console.error('Failed to load customer detail:', error);
        }
    };

    if (selectedCustomer) {
        return html`
            <div>
                <div class="content-header">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h1 class="page-title">${selectedCustomer.name}</h1>
                            <p class="page-subtitle">Customer Details</p>
                        </div>
                        <button
                            class="action-button"
                            onClick=${() => setSelectedCustomer(null)}
                        >
                            Back to Customers
                        </button>
                    </div>
                </div>
                
                <div class="detail-grid">
                    <div class="detail-card">
                        <div class="detail-label">Customer ID</div>
                        <div class="detail-value">${selectedCustomer.id}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Email</div>
                        <div class="detail-value">${selectedCustomer.email}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Phone</div>
                        <div class="detail-value">${selectedCustomer.phone}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Status</div>
                        <div class="detail-value">
                            <span class="status-badge ${selectedCustomer.status === 'active' ? 'status-active' : 'status-inactive'}">
                                ${selectedCustomer.status}
                            </span>
                        </div>
                    </div>
                </div>
                
                <div class="data-table">
                    <div class="table-header">
                        <h3 class="table-title">Customer Accounts</h3>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Account ID</th>
                                <th>Type</th>
                                <th>Balance</th>
                                <th>Status</th>
                                <th>Created</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${selectedCustomer.accounts.map(account => html`
                                <tr key=${account.id}>
                                    <td>${account.id.substring(0, 8)}...</td>
                                    <td>${account.product_type}</td>
                                    <td class="${account.balance >= 0 ? 'amount-positive' : 'amount-negative'}">
                                        ${formatCurrency(account.balance)}
                                    </td>
                                    <td>
                                        <span class="status-badge status-active">${account.status}</span>
                                    </td>
                                    <td>${formatDate(account.created_at)}</td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    if (loading) return html`<div class="loading">Loading customers...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Customers</h1>
                <p class="page-subtitle">Customer management and profiles</p>
            </div>
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Customer Directory</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Email</th>
                            <th>Phone</th>
                            <th>Accounts</th>
                            <th>Total Balance</th>
                            <th>Status</th>
                            <th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${customers.map(customer => html`
                            <tr key=${customer.id} onClick=${() => viewCustomerDetail(customer.id)}>
                                <td>${customer.name}</td>
                                <td>${customer.email}</td>
                                <td>${customer.phone}</td>
                                <td>${customer.account_count || 0}</td>
                                <td class="${customer.total_balance >= 0 ? 'amount-positive' : 'amount-negative'}">
                                    ${formatCurrency(customer.total_balance)}
                                </td>
                                <td>
                                    <span class="status-badge ${customer.status === 'active' ? 'status-active' : 'status-inactive'}">
                                        ${customer.status}
                                    </span>
                                </td>
                                <td>${formatDate(customer.created_at)}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Accounts Page
function AccountsPage() {
    const [accounts, setAccounts] = useState([]);
    const [selectedAccount, setSelectedAccount] = useState(null);
    const [loading, setLoading] = useState(true);
    const [typeFilter, setTypeFilter] = useState('');

    useEffect(() => {
        loadAccounts();
    }, [typeFilter]);

    const loadAccounts = async () => {
        try {
            setLoading(true);
            const params = typeFilter ? `?product_type=${typeFilter}` : '';
            const data = await api.get(`/api/accounts${params}`);
            setAccounts(data);
        } catch (error) {
            console.error('Failed to load accounts:', error);
        } finally {
            setLoading(false);
        }
    };

    const viewAccountDetail = async (accountId) => {
        try {
            const accountDetail = await api.get(`/api/accounts/${accountId}`);
            setSelectedAccount(accountDetail);
        } catch (error) {
            console.error('Failed to load account detail:', error);
        }
    };

    if (selectedAccount) {
        return html`
            <div>
                <div class="content-header">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h1 class="page-title">Account ${selectedAccount.id.substring(0, 8)}...</h1>
                            <p class="page-subtitle">Account Details</p>
                        </div>
                        <button
                            class="action-button"
                            onClick=${() => setSelectedAccount(null)}
                        >
                            Back to Accounts
                        </button>
                    </div>
                </div>
                
                <div class="detail-grid">
                    <div class="detail-card">
                        <div class="detail-label">Current Balance</div>
                        <div class="detail-value ${selectedAccount.balance >= 0 ? 'amount-positive' : 'amount-negative'}">
                            ${formatCurrency(selectedAccount.balance)}
                        </div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Account Type</div>
                        <div class="detail-value">${selectedAccount.product_type}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Status</div>
                        <div class="detail-value">
                            <span class="status-badge status-active">${selectedAccount.status}</span>
                        </div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Created</div>
                        <div class="detail-value">${formatDate(selectedAccount.created_at)}</div>
                    </div>
                </div>
                
                ${selectedAccount.recent_transactions && selectedAccount.recent_transactions.length > 0 && html`
                    <div class="data-table">
                        <div class="table-header">
                            <h3 class="table-title">Recent Transactions</h3>
                        </div>
                        <table>
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Type</th>
                                    <th>Amount</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${selectedAccount.recent_transactions.map(txn => html`
                                    <tr key=${txn.id}>
                                        <td>${formatDate(txn.created_at)}</td>
                                        <td>${txn.transaction_type}</td>
                                        <td class="${txn.amount >= 0 ? 'amount-positive' : 'amount-negative'}">
                                            ${formatCurrency(txn.amount)}
                                        </td>
                                        <td>
                                            <span class="status-badge status-active">${txn.status}</span>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>
        `;
    }

    if (loading) return html`<div class="loading">Loading accounts...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Accounts</h1>
                <p class="page-subtitle">Account portfolio management</p>
            </div>
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Account Portfolio</h3>
                    <div class="table-filters">
                        <select
                            class="filter-select"
                            value=${typeFilter}
                            onChange=${e => setTypeFilter(e.target.value)}
                        >
                            <option value="">All Types</option>
                            <option value="savings">Savings</option>
                            <option value="checking">Checking</option>
                            <option value="loan">Loan</option>
                            <option value="credit_line">Credit Line</option>
                        </select>
                    </div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Account ID</th>
                            <th>Customer</th>
                            <th>Type</th>
                            <th>Balance</th>
                            <th>Status</th>
                            <th>Created</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${accounts.map(account => html`
                            <tr key=${account.id} onClick=${() => viewAccountDetail(account.id)}>
                                <td>${account.id.substring(0, 8)}...</td>
                                <td>${account.customer_name || 'N/A'}</td>
                                <td>
                                    <span class="status-badge status-current">${account.product_type}</span>
                                </td>
                                <td class="${account.balance >= 0 ? 'amount-positive' : 'amount-negative'}">
                                    ${formatCurrency(account.balance)}
                                </td>
                                <td>
                                    <span class="status-badge status-active">${account.status}</span>
                                </td>
                                <td>${formatDate(account.created_at)}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Transactions Page
function TransactionsPage() {
    const [transactions, setTransactions] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadTransactions();
    }, []);

    const loadTransactions = async () => {
        try {
            setLoading(true);
            const data = await api.get('/api/transactions?limit=50');
            setTransactions(data);
        } catch (error) {
            console.error('Failed to load transactions:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return html`<div class="loading">Loading transactions...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Transactions</h1>
                <p class="page-subtitle">Transaction history and monitoring</p>
            </div>
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Transaction History</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Transaction ID</th>
                            <th>Type</th>
                            <th>From Account</th>
                            <th>To Account</th>
                            <th>Amount</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${transactions.map(txn => html`
                            <tr key=${txn.id}>
                                <td>${formatDate(txn.created_at)}</td>
                                <td>${txn.id.substring(0, 8)}...</td>
                                <td>
                                    <span class="status-badge status-current">${txn.transaction_type}</span>
                                </td>
                                <td>${txn.from_account_name || 'N/A'}</td>
                                <td>${txn.to_account_name || 'N/A'}</td>
                                <td class="${txn.amount >= 0 ? 'amount-positive' : 'amount-negative'}">
                                    ${formatCurrency(txn.amount)}
                                </td>
                                <td>
                                    <span class="status-badge status-active">${txn.status}</span>
                                </td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Loans Page
function LoansPage() {
    const [loans, setLoans] = useState([]);
    const [selectedLoan, setSelectedLoan] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadLoans();
    }, []);

    const loadLoans = async () => {
        try {
            setLoading(true);
            const data = await api.get('/api/loans');
            setLoans(data);
        } catch (error) {
            console.error('Failed to load loans:', error);
        } finally {
            setLoading(false);
        }
    };

    const viewLoanDetail = async (loanId) => {
        try {
            const loanDetail = await api.get(`/api/loans/${loanId}`);
            setSelectedLoan(loanDetail);
        } catch (error) {
            console.error('Failed to load loan detail:', error);
        }
    };

    if (selectedLoan) {
        return html`
            <div>
                <div class="content-header">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h1 class="page-title">${selectedLoan.customer} - Loan</h1>
                            <p class="page-subtitle">Loan Details & Amortization</p>
                        </div>
                        <button
                            class="action-button"
                            onClick=${() => setSelectedLoan(null)}
                        >
                            Back to Loans
                        </button>
                    </div>
                </div>
                
                <div class="detail-grid">
                    <div class="detail-card">
                        <div class="detail-label">Principal Amount</div>
                        <div class="detail-value">${formatCurrency(selectedLoan.terms.principal_amount)}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Current Balance</div>
                        <div class="detail-value amount-negative">${formatCurrency(selectedLoan.current_status.current_balance)}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Interest Rate</div>
                        <div class="detail-value">${selectedLoan.terms.annual_interest_rate.toFixed(2)}%</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Term</div>
                        <div class="detail-value">${selectedLoan.terms.term_months} months</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Status</div>
                        <div class="detail-value">
                            <span class="status-badge ${selectedLoan.current_status.state === 'active' ? 'status-active' : 'status-inactive'}">
                                ${selectedLoan.current_status.state}
                            </span>
                        </div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Days Past Due</div>
                        <div class="detail-value ${selectedLoan.current_status.days_past_due > 0 ? 'amount-negative' : ''}">
                            ${selectedLoan.current_status.days_past_due} days
                        </div>
                    </div>
                </div>
                
                ${selectedLoan.amortization_schedule && selectedLoan.amortization_schedule.length > 0 && html`
                    <div class="data-table">
                        <div class="table-header">
                            <h3 class="table-title">Amortization Schedule</h3>
                        </div>
                        <table>
                            <thead>
                                <tr>
                                    <th>Payment #</th>
                                    <th>Date</th>
                                    <th>Payment Amount</th>
                                    <th>Principal</th>
                                    <th>Interest</th>
                                    <th>Remaining Balance</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${selectedLoan.amortization_schedule.slice(0, 12).map(payment => html`
                                    <tr key=${payment.payment_number}>
                                        <td>${payment.payment_number}</td>
                                        <td>${formatDate(payment.payment_date)}</td>
                                        <td>${formatCurrency(payment.payment_amount)}</td>
                                        <td>${formatCurrency(payment.principal_amount)}</td>
                                        <td>${formatCurrency(payment.interest_amount)}</td>
                                        <td>${formatCurrency(payment.remaining_balance)}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>
        `;
    }

    if (loading) return html`<div class="loading">Loading loans...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Loans</h1>
                <p class="page-subtitle">Loan portfolio management</p>
            </div>
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Loan Portfolio</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Loan Number</th>
                            <th>Customer</th>
                            <th>Type</th>
                            <th>Principal</th>
                            <th>Balance</th>
                            <th>Rate</th>
                            <th>Status</th>
                            <th>Next Payment</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${loans.map(loan => html`
                            <tr key=${loan.id} onClick=${() => viewLoanDetail(loan.id)}>
                                <td>${loan.loan_number}</td>
                                <td>${loan.customer_name}</td>
                                <td>
                                    <span class="status-badge status-current">${loan.type}</span>
                                </td>
                                <td>${formatCurrency(loan.principal)}</td>
                                <td class="amount-negative">${formatCurrency(loan.balance)}</td>
                                <td>${loan.rate.toFixed(2)}%</td>
                                <td>
                                    <span class="status-badge ${loan.status === 'active' ? 'status-active' : 'status-inactive'}">
                                        ${loan.status}
                                    </span>
                                </td>
                                <td>${formatDate(loan.next_payment_date)}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Credit Lines Page
function CreditLinesPage() {
    const [creditLines, setCreditLines] = useState([]);
    const [selectedCreditLine, setSelectedCreditLine] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadCreditLines();
    }, []);

    const loadCreditLines = async () => {
        try {
            setLoading(true);
            const data = await api.get('/api/credit-lines');
            setCreditLines(data);
        } catch (error) {
            console.error('Failed to load credit lines:', error);
        } finally {
            setLoading(false);
        }
    };

    const viewCreditLineDetail = async (creditLineId) => {
        try {
            const creditLineDetail = await api.get(`/api/credit-lines/${creditLineId}`);
            setSelectedCreditLine(creditLineDetail);
        } catch (error) {
            console.error('Failed to load credit line detail:', error);
        }
    };

    if (selectedCreditLine) {
        return html`
            <div>
                <div class="content-header">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h1 class="page-title">${selectedCreditLine.customer} - Credit Line</h1>
                            <p class="page-subtitle">Credit Line Details & Statements</p>
                        </div>
                        <button
                            class="action-button"
                            onClick=${() => setSelectedCreditLine(null)}
                        >
                            Back to Credit Lines
                        </button>
                    </div>
                </div>
                
                <div class="detail-grid">
                    <div class="detail-card">
                        <div class="detail-label">Credit Limit</div>
                        <div class="detail-value">${formatCurrency(selectedCreditLine.credit_info.credit_limit)}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Current Balance</div>
                        <div class="detail-value amount-negative">${formatCurrency(selectedCreditLine.credit_info.current_balance)}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Available Credit</div>
                        <div class="detail-value amount-positive">${formatCurrency(selectedCreditLine.credit_info.available_credit)}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Status</div>
                        <div class="detail-value">
                            <span class="status-badge status-active">${selectedCreditLine.credit_info.status}</span>
                        </div>
                    </div>
                </div>
                
                ${selectedCreditLine.statements && selectedCreditLine.statements.length > 0 && html`
                    <div class="data-table">
                        <div class="table-header">
                            <h3 class="table-title">Statements</h3>
                        </div>
                        <table>
                            <thead>
                                <tr>
                                    <th>Statement Date</th>
                                    <th>Due Date</th>
                                    <th>Balance</th>
                                    <th>Minimum Payment</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${selectedCreditLine.statements.map(statement => html`
                                    <tr key=${statement.id}>
                                        <td>${formatDate(statement.statement_date)}</td>
                                        <td>${formatDate(statement.due_date)}</td>
                                        <td class="amount-negative">${formatCurrency(statement.current_balance)}</td>
                                        <td>${formatCurrency(statement.minimum_payment_due)}</td>
                                        <td>
                                            <span class="status-badge status-current">${statement.status}</span>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                `}
            </div>
        `;
    }

    if (loading) return html`<div class="loading">Loading credit lines...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Credit Lines</h1>
                <p class="page-subtitle">Credit line portfolio management</p>
            </div>
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Credit Line Portfolio</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Account Number</th>
                            <th>Customer</th>
                            <th>Credit Limit</th>
                            <th>Used</th>
                            <th>Available</th>
                            <th>Status</th>
                            <th>Utilization</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${creditLines.map(creditLine => html`
                            <tr key=${creditLine.id} onClick=${() => viewCreditLineDetail(creditLine.id)}>
                                <td>${creditLine.account_number}</td>
                                <td>${creditLine.customer_name}</td>
                                <td>${formatCurrency(creditLine.limit)}</td>
                                <td class="amount-negative">${formatCurrency(creditLine.used)}</td>
                                <td class="amount-positive">${formatCurrency(creditLine.available)}</td>
                                <td>
                                    <span class="status-badge status-active">${creditLine.status}</span>
                                </td>
                                <td>${creditLine.limit > 0 ? ((creditLine.used / creditLine.limit) * 100).toFixed(1) : 0}%</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Collections Page
function CollectionsPage() {
    const [cases, setCases] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadCollectionsData();
    }, []);

    const loadCollectionsData = async () => {
        try {
            setLoading(true);
            const [casesData, statsData] = await Promise.all([
                api.get('/api/collections/cases'),
                api.get('/api/collections/stats')
            ]);
            setCases(casesData);
            setStats(statsData);
        } catch (error) {
            console.error('Failed to load collections data:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return html`<div class="loading">Loading collections...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Collections</h1>
                <p class="page-subtitle">Delinquency management and recovery</p>
            </div>
            
            ${stats && html`
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-header">
                            <h3 class="stat-title">Total Cases</h3>
                        </div>
                        <div class="stat-value">${stats.total_cases}</div>
                        <div class="stat-change">Active delinquent accounts</div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-header">
                            <h3 class="stat-title">Total Overdue</h3>
                        </div>
                        <div class="stat-value amount-negative">${formatCurrency(stats.total_overdue_amount)}</div>
                        <div class="stat-change">Outstanding balance</div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-header">
                            <h3 class="stat-title">Recovery Rate</h3>
                        </div>
                        <div class="stat-value">${stats.recovery_rate}%</div>
                        <div class="stat-change">6-month average</div>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-header">
                            <h3 class="stat-title">Cases Resolved (6M)</h3>
                        </div>
                        <div class="stat-value">${stats.cases_resolved_6m}</div>
                        <div class="stat-change">Successfully closed</div>
                    </div>
                </div>
                
                <div class="chart-container">
                    <h3 class="chart-title">Days Past Due Distribution</h3>
                    ${Object.entries(stats.dpd_distribution).map(([bucket, count]) => html`
                        <div key=${bucket} class="dpd-bar">
                            <div class="dpd-label">${bucket === '0' ? 'Current' : bucket + ' days'}</div>
                            <div class="dpd-bar-fill bucket-${bucket.replace('+', '')}">
                                <div style="width: ${count > 0 ? Math.max(10, (count / Math.max(...Object.values(stats.dpd_distribution))) * 100) : 0}%; height: 100%; opacity: 0.7;"></div>
                            </div>
                            <div class="dpd-value">${count}</div>
                        </div>
                    `)}</div>
                </div>
            `}
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Collection Cases</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Case ID</th>
                            <th>Customer</th>
                            <th>Amount Overdue</th>
                            <th>Days Past Due</th>
                            <th>Status</th>
                            <th>Priority</th>
                            <th>Assigned To</th>
                            <th>Account Type</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${cases.map(case_ => html`
                            <tr key=${case_.id}>
                                <td>${case_.case_id}</td>
                                <td>${case_.customer_name}</td>
                                <td class="amount-negative">${formatCurrency(case_.amount_overdue)}</td>
                                <td class="${case_.days_past_due > 90 ? 'priority-5' : case_.days_past_due > 60 ? 'priority-4' : case_.days_past_due > 30 ? 'priority-3' : 'priority-2'}">
                                    ${case_.days_past_due} days
                                </td>
                                <td>
                                    <span class="status-badge ${case_.status === 'current' ? 'status-current' : case_.status === 'early' ? 'status-early' : case_.status === 'serious' ? 'status-serious' : 'status-default'}">
                                        ${case_.status}
                                    </span>
                                </td>
                                <td class="priority-${case_.priority}">P${case_.priority}</td>
                                <td>${case_.assigned_to}</td>
                                <td>
                                    <span class="status-badge status-current">${case_.account_type}</span>
                                </td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Products Page
function ProductsPage() {
    const [products, setProducts] = useState([]);
    const [selectedProduct, setSelectedProduct] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadProducts();
    }, []);

    const loadProducts = async () => {
        try {
            setLoading(true);
            const data = await api.get('/api/products');
            setProducts(data);
        } catch (error) {
            console.error('Failed to load products:', error);
        } finally {
            setLoading(false);
        }
    };

    const viewProductDetail = async (productId) => {
        try {
            const productDetail = await api.get(`/api/products/${productId}`);
            setSelectedProduct(productDetail);
        } catch (error) {
            console.error('Failed to load product detail:', error);
        }
    };

    if (selectedProduct) {
        return html`
            <div>
                <div class="content-header">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h1 class="page-title">${selectedProduct.name}</h1>
                            <p class="page-subtitle">Product Details & Configuration</p>
                        </div>
                        <button
                            class="action-button"
                            onClick=${() => setSelectedProduct(null)}
                        >
                            Back to Products
                        </button>
                    </div>
                </div>
                
                <div class="detail-grid">
                    <div class="detail-card">
                        <div class="detail-label">Product Code</div>
                        <div class="detail-value">${selectedProduct.product_code}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Type</div>
                        <div class="detail-value">${selectedProduct.product_type}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Status</div>
                        <div class="detail-value">
                            <span class="status-badge ${selectedProduct.status === 'active' ? 'status-active' : 'status-inactive'}">
                                ${selectedProduct.status}
                            </span>
                        </div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Currency</div>
                        <div class="detail-value">${selectedProduct.currency}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Active Accounts</div>
                        <div class="detail-value">${selectedProduct.performance_metrics.total_accounts}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Total Balance</div>
                        <div class="detail-value">${formatCurrency(selectedProduct.performance_metrics.total_balance)}</div>
                    </div>
                </div>
                
                <div class="data-table">
                    <div class="table-header">
                        <h3 class="table-title">Product Description</h3>
                    </div>
                    <div style="padding: 1.5rem;">
                        <p>${selectedProduct.description}</p>
                    </div>
                </div>
            </div>
        `;
    }

    if (loading) return html`<div class="loading">Loading products...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Products</h1>
                <p class="page-subtitle">Product catalog and configuration</p>
            </div>
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Product Catalog</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Product Name</th>
                            <th>Code</th>
                            <th>Type</th>
                            <th>Rate Range</th>
                            <th>Term Range</th>
                            <th>Status</th>
                            <th>Active Accounts</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${products.map(product => html`
                            <tr key=${product.id} onClick=${() => viewProductDetail(product.id)}>
                                <td>${product.name}</td>
                                <td>${product.product_code}</td>
                                <td>
                                    <span class="status-badge status-current">${product.type}</span>
                                </td>
                                <td>${product.rate_range}</td>
                                <td>${product.term_range}</td>
                                <td>
                                    <span class="status-badge ${product.status === 'active' ? 'status-active' : 'status-inactive'}">
                                        ${product.status}
                                    </span>
                                </td>
                                <td>${product.active_accounts}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Users & RBAC Page (keeping existing implementation)
function UsersPage() {
    const [users, setUsers] = useState([]);
    const [roles, setRoles] = useState([]);
    const [sessions, setSessions] = useState([]);
    const [selectedUser, setSelectedUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('users');

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            setLoading(true);
            const [usersRes, rolesRes, sessionsRes] = await Promise.all([
                api.get('/api/users'),
                api.get('/api/roles'),
                api.get('/api/sessions')
            ]);
            
            setUsers(usersRes.users);
            setRoles(rolesRes.roles);
            setSessions(sessionsRes.sessions);
        } catch (error) {
            console.error('Failed to load users data:', error);
        } finally {
            setLoading(false);
        }
    };

    const viewUserDetail = async (userId) => {
        try {
            const userDetail = await api.get(`/api/users/${userId}`);
            setSelectedUser(userDetail);
        } catch (error) {
            console.error('Failed to load user detail:', error);
        }
    };

    if (loading) return html`<div class="loading">Loading users data...</div>`;

    if (selectedUser) {
        return html`
            <div>
                <div class="content-header">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <h1 class="page-title">${selectedUser.user.username}</h1>
                            <p class="page-subtitle">User Details</p>
                        </div>
                        <button
                            class="action-button"
                            onClick=${() => setSelectedUser(null)}
                        >
                            Back to Users
                        </button>
                    </div>
                </div>
                
                <div class="detail-grid">
                    <div class="detail-card">
                        <div class="detail-label">Full Name</div>
                        <div class="detail-value">${selectedUser.user.full_name}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Email</div>
                        <div class="detail-value">${selectedUser.user.email}</div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Status</div>
                        <div class="detail-value">
                            <span class="status-badge ${selectedUser.user.is_active ? 'status-active' : 'status-inactive'}">
                                ${selectedUser.user.is_active ? 'Active' : 'Inactive'}
                            </span>
                        </div>
                    </div>
                    <div class="detail-card">
                        <div class="detail-label">Last Login</div>
                        <div class="detail-value">${formatDate(selectedUser.user.last_login)}</div>
                    </div>
                </div>
                
                <div class="data-table">
                    <div class="table-header">
                        <h3 class="table-title">User Roles</h3>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Role Name</th>
                                <th>Description</th>
                                <th>Type</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${selectedUser.roles.map(role => html`
                                <tr key=${role.id}>
                                    <td>${role.name}</td>
                                    <td>${role.description}</td>
                                    <td>
                                        <span class="status-badge ${role.is_system_role ? 'status-current' : 'status-active'}">
                                            ${role.is_system_role ? 'System' : 'Custom'}
                                        </span>
                                    </td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Users & RBAC</h1>
                <p class="page-subtitle">User management and access control</p>
            </div>
            
            <div style="margin-bottom: 2rem;">
                <div style="display: flex; gap: 1rem; border-bottom: 1px solid #e2e8f0;">
                    ${['users', 'roles', 'sessions'].map(tab => html`
                        <button
                            key=${tab}
                            style="padding: 1rem 1.5rem; border: none; background: ${activeTab === tab ? '#1A3C78' : 'transparent'}; color: ${activeTab === tab ? 'white' : '#64748b'}; border-radius: 8px 8px 0 0; cursor: pointer; font-weight: 500; text-transform: capitalize;"
                            onClick=${() => setActiveTab(tab)}
                        >
                            ${tab}
                        </button>
                    `)}
                </div>
            </div>

            ${activeTab === 'users' && html`
                <div class="data-table">
                    <div class="table-header">
                        <h3 class="table-title">System Users</h3>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Username</th>
                                <th>Full Name</th>
                                <th>Email</th>
                                <th>Status</th>
                                <th>Roles</th>
                                <th>Last Login</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${users.map(user => html`
                                <tr key=${user.id} onClick=${() => viewUserDetail(user.id)}>
                                    <td>${user.username}</td>
                                    <td>${user.full_name}</td>
                                    <td>${user.email}</td>
                                    <td>
                                        <span class="status-badge ${user.is_active ? 'status-active' : 'status-inactive'}">
                                            ${user.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td>
                                        ${user.roles.map(role => html`
                                            <span key=${role.id} class="status-badge status-current" style="margin-right: 0.25rem;">
                                                ${role.name}
                                            </span>
                                        `)}
                                    </td>
                                    <td>${formatDate(user.last_login)}</td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            `}

            ${activeTab === 'roles' && html`
                <div class="data-table">
                    <div class="table-header">
                        <h3 class="table-title">System Roles</h3>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>Role Name</th>
                                <th>Description</th>
                                <th>Type</th>
                                <th>Permissions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${roles.map(role => html`
                                <tr key=${role.id}>
                                    <td>${role.name}</td>
                                    <td>${role.description}</td>
                                    <td>
                                        <span class="status-badge ${role.is_system_role ? 'status-current' : 'status-active'}">
                                            ${role.is_system_role ? 'System' : 'Custom'}
                                        </span>
                                    </td>
                                    <td>${role.permission_count} permissions</td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            `}

            ${activeTab === 'sessions' && html`
                <div class="data-table">
                    <div class="table-header">
                        <h3 class="table-title">Active Sessions</h3>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Session ID</th>
                                <th>IP Address</th>
                                <th>Created</th>
                                <th>Expires</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${sessions.map(session => html`
                                <tr key=${session.id}>
                                    <td>${session.username}</td>
                                    <td style="font-family: monospace; font-size: 0.8rem;">${session.id.substring(0, 12)}...</td>
                                    <td>${session.ip_address || 'Unknown'}</td>
                                    <td>${formatDate(session.created_at)}</td>
                                    <td>${formatDate(session.expires_at)}</td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            `}
        </div>
    `;
}

// Audit Trail Page (keeping existing implementation but simplified)
function AuditPage() {
    const [events, setEvents] = useState([]);
    const [chainVerification, setChainVerification] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadEvents();
        verifyChain();
    }, []);

    const loadEvents = async () => {
        try {
            setLoading(true);
            const eventsRes = await api.get('/api/audit');
            setEvents(eventsRes.events);
        } catch (error) {
            console.error('Failed to load audit events:', error);
        } finally {
            setLoading(false);
        }
    };

    const verifyChain = async () => {
        try {
            const verification = await api.get('/api/audit/verify');
            setChainVerification(verification);
        } catch (error) {
            console.error('Failed to verify chain:', error);
        }
    };

    if (loading) return html`<div class="loading">Loading audit trail...</div>`;

    return html`
        <div>
            <div class="content-header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h1 class="page-title">Audit Trail</h1>
                        <p class="page-subtitle">System audit log and hash chain verification</p>
                    </div>
                    ${chainVerification && html`
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <span style="font-weight: 600; color: ${chainVerification.chain_valid ? '#16a34a' : '#dc2626'};">
                                Chain Status: ${chainVerification.chain_valid ? 'Valid' : 'Invalid'}
                            </span>
                            <div style="width: 12px; height: 12px; border-radius: 50%; background: ${chainVerification.chain_valid ? '#16a34a' : '#dc2626'};"></div>
                        </div>
                    `}
                </div>
            </div>

            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Audit Events</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Event Type</th>
                            <th>User</th>
                            <th>Entity</th>
                            <th>Description</th>
                            <th>Hash</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${events.map(event => html`
                            <tr key=${event.id}>
                                <td>${formatDate(event.timestamp)}</td>
                                <td>
                                    <span class="status-badge status-current">${event.event_type}</span>
                                </td>
                                <td>${event.username}</td>
                                <td style="font-family: monospace; font-size: 0.8rem;">
                                    ${event.entity_type}/${event.entity_id.substring(0, 8)}...
                                </td>
                                <td>${event.description}</td>
                                <td style="font-family: monospace; font-size: 0.8rem;">
                                    ${event.hash.substring(0, 8)}...
                                </td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Workflows Page (simplified version)
function WorkflowsPage() {
    const [workflows, setWorkflows] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadWorkflows();
    }, []);

    const loadWorkflows = async () => {
        try {
            setLoading(true);
            const workflowsRes = await api.get('/api/workflows');
            setWorkflows(workflowsRes.workflows);
        } catch (error) {
            console.error('Failed to load workflows:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return html`<div class="loading">Loading workflows...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Workflows</h1>
                <p class="page-subtitle">Active workflow instances</p>
            </div>
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Active Workflows</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Entity</th>
                            <th>Status</th>
                            <th>Current Step</th>
                            <th>Started</th>
                            <th>SLA Deadline</th>
                            <th>Initiated By</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${workflows.map(workflow => html`
                            <tr key=${workflow.id}>
                                <td>
                                    <span class="status-badge status-current">${workflow.type}</span>
                                </td>
                                <td style="font-family: monospace; font-size: 0.8rem;">
                                    ${workflow.entity_type}/${workflow.entity_id.substring(0, 8)}...
                                </td>
                                <td>
                                    <span class="status-badge ${workflow.status === 'active' ? 'status-active' : 'status-pending'}">
                                        ${workflow.status}
                                    </span>
                                </td>
                                <td>${workflow.current_step || 'N/A'}</td>
                                <td>${formatDate(workflow.created_at)}</td>
                                <td>${formatDate(workflow.sla_deadline)}</td>
                                <td>${workflow.initiated_by}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Notifications Page (simplified version)
function NotificationsPage() {
    const [notifications, setNotifications] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            setLoading(true);
            const [notificationsRes, statsRes] = await Promise.all([
                api.get('/api/notifications'),
                api.get('/api/notifications/stats')
            ]);
            
            setNotifications(notificationsRes.notifications);
            setStats(statsRes);
        } catch (error) {
            console.error('Failed to load notifications:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return html`<div class="loading">Loading notifications...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Notifications</h1>
                <p class="page-subtitle">System notifications and messaging</p>
            </div>
            
            ${stats && html`
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-header">
                            <h3 class="stat-title">Sent</h3>
                        </div>
                        <div class="stat-value amount-positive">${stats.sent || 0}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <h3 class="stat-title">Delivered</h3>
                        </div>
                        <div class="stat-value amount-positive">${stats.delivered || 0}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <h3 class="stat-title">Failed</h3>
                        </div>
                        <div class="stat-value amount-negative">${stats.failed || 0}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <h3 class="stat-title">Pending</h3>
                        </div>
                        <div class="stat-value">${stats.pending || 0}</div>
                    </div>
                </div>
            `}
            
            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Notification Log</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Recipient</th>
                            <th>Type</th>
                            <th>Channel</th>
                            <th>Status</th>
                            <th>Subject</th>
                            <th>Created</th>
                            <th>Sent</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${notifications.map(notification => html`
                            <tr key=${notification.id}>
                                <td>${notification.recipient}</td>
                                <td>
                                    <span class="status-badge status-current">${notification.type}</span>
                                </td>
                                <td>
                                    <span class="status-badge status-active">${notification.channel}</span>
                                </td>
                                <td>
                                    <span class="status-badge ${notification.status === 'sent' ? 'status-active' : notification.status === 'failed' ? 'status-overdue' : 'status-pending'}">
                                        ${notification.status}
                                    </span>
                                </td>
                                <td>${notification.subject}</td>
                                <td>${formatDate(notification.created_at)}</td>
                                <td>${formatDate(notification.sent_at)}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Compliance Page (simplified version)
function CompliancePage() {
    const [alerts, setAlerts] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadAlerts();
    }, []);

    const loadAlerts = async () => {
        try {
            setLoading(true);
            const alertsRes = await api.get('/api/compliance/alerts');
            setAlerts(alertsRes.alerts);
        } catch (error) {
            console.error('Failed to load compliance alerts:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return html`<div class="loading">Loading compliance data...</div>`;

    const pendingAlerts = alerts.filter(a => a.status === 'pending');
    const resolvedAlerts = alerts.filter(a => a.status === 'resolved');

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Compliance</h1>
                <p class="page-subtitle">Compliance monitoring and alerts</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Pending Alerts</h3>
                    </div>
                    <div class="stat-value amount-negative">${pendingAlerts.length}</div>
                    <div class="stat-change">Require attention</div>
                </div>
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Resolved Alerts</h3>
                    </div>
                    <div class="stat-value amount-positive">${resolvedAlerts.length}</div>
                    <div class="stat-change">Closed cases</div>
                </div>
                <div class="stat-card">
                    <div class="stat-header">
                        <h3 class="stat-title">Total Alerts</h3>
                    </div>
                    <div class="stat-value">${alerts.length}</div>
                    <div class="stat-change">All time</div>
                </div>
            </div>

            <div class="data-table">
                <div class="table-header">
                    <h3 class="table-title">Compliance Alerts</h3>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Customer ID</th>
                            <th>Type</th>
                            <th>Severity</th>
                            <th>Status</th>
                            <th>Risk Score</th>
                            <th>Created</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${alerts.map(alert => html`
                            <tr key=${alert.id}>
                                <td style="font-family: monospace; font-size: 0.8rem;">
                                    ${alert.customer_id.substring(0, 8)}...
                                </td>
                                <td>
                                    <span class="status-badge status-current">${alert.alert_type}</span>
                                </td>
                                <td class="${alert.severity === 'high' ? 'priority-5' : alert.severity === 'medium' ? 'priority-3' : 'priority-1'}">
                                    ${alert.severity}
                                </td>
                                <td>
                                    <span class="status-badge ${alert.status === 'pending' ? 'status-pending' : 'status-active'}">
                                        ${alert.status}
                                    </span>
                                </td>
                                <td class="${alert.risk_score >= 80 ? 'priority-5' : alert.risk_score >= 60 ? 'priority-3' : 'priority-1'}">
                                    ${alert.risk_score}/100
                                </td>
                                <td>${formatDate(alert.created_at)}</td>
                                <td>${alert.description}</td>
                            </tr>
                        `)}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// Settings Page (simplified version)
function SettingsPage() {
    const [settings, setSettings] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadSettings();
    }, []);

    const loadSettings = async () => {
        try {
            setLoading(true);
            const settingsRes = await api.get('/api/settings');
            setSettings(settingsRes);
        } catch (error) {
            console.error('Failed to load settings:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) return html`<div class="loading">Loading system settings...</div>`;

    return html`
        <div>
            <div class="content-header">
                <h1 class="page-title">Settings</h1>
                <p class="page-subtitle">System configuration and status</p>
            </div>
            
            <div class="detail-grid">
                <div class="detail-card">
                    <div class="detail-label">Database Type</div>
                    <div class="detail-value">${settings.database.type}</div>
                </div>
                <div class="detail-card">
                    <div class="detail-label">Database Status</div>
                    <div class="detail-value">
                        <span class="status-badge ${settings.database.status === 'Connected' ? 'status-active' : 'status-overdue'}">
                            ${settings.database.status}
                        </span>
                    </div>
                </div>
                <div class="detail-card">
                    <div class="detail-label">Database Size</div>
                    <div class="detail-value">${settings.database.size_mb} MB</div>
                </div>
                <div class="detail-card">
                    <div class="detail-label">Encryption Status</div>
                    <div class="detail-value">
                        <span class="status-badge ${settings.encryption.status === 'Enabled' ? 'status-active' : 'status-inactive'}">
                            ${settings.encryption.status}
                        </span>
                    </div>
                </div>
                <div class="detail-card">
                    <div class="detail-label">System Version</div>
                    <div class="detail-value">${settings.system.version}</div>
                </div>
                <div class="detail-card">
                    <div class="detail-label">System Uptime</div>
                    <div class="detail-value">${settings.system.uptime_hours} hours</div>
                </div>
            </div>
        </div>
    `;
}

// Main App Component
function App() {
    const [currentPage, setCurrentPage] = useState('overview'); // Changed default to overview

    const renderPage = () => {
        switch (currentPage) {
            case 'overview': return html`<${OverviewPage} />`;
            case 'customers': return html`<${CustomersPage} />`;
            case 'accounts': return html`<${AccountsPage} />`;
            case 'transactions': return html`<${TransactionsPage} />`;
            case 'loans': return html`<${LoansPage} />`;
            case 'credit-lines': return html`<${CreditLinesPage} />`;
            case 'collections': return html`<${CollectionsPage} />`;
            case 'products': return html`<${ProductsPage} />`;
            case 'users': return html`<${UsersPage} />`;
            case 'audit': return html`<${AuditPage} />`;
            case 'workflows': return html`<${WorkflowsPage} />`;
            case 'notifications': return html`<${NotificationsPage} />`;
            case 'compliance': return html`<${CompliancePage} />`;
            case 'settings': return html`<${SettingsPage} />`;
            default: return html`<${OverviewPage} />`;
        }
    };

    return html`
        <div class="dashboard-container">
            <${Sidebar} currentPage=${currentPage} onPageChange=${setCurrentPage} />
            <${MainContent}>
                ${renderPage()}
            <//>
        </div>
    `;
}

// Render the app
render(html`<${App} />`, document.getElementById('app'));