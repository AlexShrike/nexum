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
    }).format(amount);
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
    const navItems = [
        { id: 'users', label: 'Users & RBAC', icon: '👥' },
        { id: 'audit', label: 'Audit Trail', icon: '📋' },
        { id: 'workflows', label: 'Workflows', icon: '🔄' },
        { id: 'notifications', label: 'Notifications', icon: '📧' },
        { id: 'compliance', label: 'Compliance', icon: '⚖️' },
        { id: 'settings', label: 'Settings', icon: '⚙️' }
    ];

    return html`
        <div class="sidebar w-64 h-screen fixed left-0 top-0 text-white p-6">
            <div class="mb-8">
                <h1 class="text-xl font-bold">Nexum Banking</h1>
                <p class="text-sm opacity-75">Admin Dashboard</p>
            </div>
            
            <nav class="space-y-2">
                ${navItems.map(item => html`
                    <button
                        key=${item.id}
                        class="nav-item ${currentPage === item.id ? 'active' : ''} w-full text-left px-4 py-3 rounded transition-colors flex items-center space-x-3"
                        onClick=${() => onPageChange(item.id)}
                    >
                        <span class="text-lg">${item.icon}</span>
                        <span>${item.label}</span>
                    </button>
                `)}
            </nav>
        </div>
    `;
}

// Main content area
function MainContent({ children }) {
    return html`
        <div class="ml-64 p-8">
            ${children}
        </div>
    `;
}

// Users & RBAC Page
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

    if (loading) return html`<div class="text-center py-8">Loading users data...</div>`;

    if (selectedUser) {
        return html`
            <div>
                <div class="flex items-center justify-between mb-6">
                    <h2 class="text-2xl font-bold text-gray-800">User Detail</h2>
                    <button
                        class="px-4 py-2 text-sm bg-gray-500 text-white rounded hover:bg-gray-600"
                        onClick=${() => setSelectedUser(null)}
                    >
                        Back to Users
                    </button>
                </div>
                
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="card p-6">
                        <h3 class="text-lg font-semibold mb-4">User Information</h3>
                        <div class="space-y-2">
                            <p><strong>Username:</strong> ${selectedUser.user.username}</p>
                            <p><strong>Full Name:</strong> ${selectedUser.user.full_name}</p>
                            <p><strong>Email:</strong> ${selectedUser.user.email}</p>
                            <p><strong>Status:</strong> 
                                <span class="${selectedUser.user.is_active ? 'text-green-600' : 'text-red-600'}">
                                    ${selectedUser.user.is_active ? 'Active' : 'Inactive'}
                                </span>
                                ${selectedUser.user.is_locked && html`<span class="text-red-600 ml-2">(Locked)</span>`}
                            </p>
                            <p><strong>Last Login:</strong> ${formatDate(selectedUser.user.last_login)}</p>
                            <p><strong>Created:</strong> ${formatDate(selectedUser.user.created_at)}</p>
                            <p><strong>Created By:</strong> ${selectedUser.user.created_by}</p>
                        </div>
                    </div>
                    
                    <div class="card p-6">
                        <h3 class="text-lg font-semibold mb-4">Roles & Permissions</h3>
                        <div class="mb-4">
                            <strong>Roles:</strong>
                            <div class="mt-2">
                                ${selectedUser.roles.map(role => html`
                                    <span key=${role.id} class="inline-block bg-blue-100 text-blue-800 px-2 py-1 rounded text-sm mr-2 mb-1">
                                        ${role.name}
                                    </span>
                                `)}
                            </div>
                        </div>
                        <div>
                            <strong>Total Permissions:</strong> ${selectedUser.permissions.length}
                            <div class="mt-2 max-h-40 overflow-y-auto">
                                ${selectedUser.permissions.map(perm => html`
                                    <span key=${perm} class="inline-block bg-gray-100 text-gray-700 px-2 py-1 rounded text-xs mr-1 mb-1">
                                        ${perm}
                                    </span>
                                `)}
                            </div>
                        </div>
                    </div>
                    
                    <div class="card p-6 lg:col-span-2">
                        <h3 class="text-lg font-semibold mb-4">Active Sessions</h3>
                        ${selectedUser.active_sessions.length === 0 ? html`
                            <p class="text-gray-600">No active sessions</p>
                        ` : html`
                            <div class="overflow-x-auto">
                                <table class="w-full text-sm">
                                    <thead class="bg-gray-50">
                                        <tr>
                                            <th class="px-4 py-2 text-left">Session ID</th>
                                            <th class="px-4 py-2 text-left">IP Address</th>
                                            <th class="px-4 py-2 text-left">Created</th>
                                            <th class="px-4 py-2 text-left">Expires</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${selectedUser.active_sessions.map(session => html`
                                            <tr key=${session.id} class="border-t">
                                                <td class="px-4 py-2 font-mono text-xs">${session.id.substring(0, 8)}...</td>
                                                <td class="px-4 py-2">${session.ip_address || 'Unknown'}</td>
                                                <td class="px-4 py-2">${formatDate(session.created_at)}</td>
                                                <td class="px-4 py-2">${formatDate(session.expires_at)}</td>
                                            </tr>
                                        `)}
                                    </tbody>
                                </table>
                            </div>
                        `}
                    </div>
                </div>
            </div>
        `;
    }

    return html`
        <div>
            <h2 class="text-2xl font-bold text-gray-800 mb-6">Users & RBAC</h2>
            
            <div class="mb-6">
                <nav class="flex space-x-1">
                    ${['users', 'roles', 'sessions'].map(tab => html`
                        <button
                            key=${tab}
                            class="px-4 py-2 text-sm font-medium rounded-lg ${activeTab === tab ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:text-gray-700'}"
                            onClick=${() => setActiveTab(tab)}
                        >
                            ${tab.charAt(0).toUpperCase() + tab.slice(1)}
                        </button>
                    `)}
                </nav>
            </div>

            ${activeTab === 'users' && html`
                <div class="card">
                    <div class="p-6 border-b">
                        <h3 class="text-lg font-semibold">System Users</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Username</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Full Name</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Roles</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Login</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-200">
                                ${users.map(user => html`
                                    <tr key=${user.id}>
                                        <td class="px-6 py-4 font-medium">${user.username}</td>
                                        <td class="px-6 py-4">${user.full_name}</td>
                                        <td class="px-6 py-4 text-sm">${user.email}</td>
                                        <td class="px-6 py-4">
                                            <span class="${user.is_active ? 'text-green-600' : 'text-red-600'} text-sm">
                                                ${user.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                            ${user.is_locked && html`<span class="text-red-600 text-xs ml-1">(Locked)</span>`}
                                        </td>
                                        <td class="px-6 py-4">
                                            ${user.roles.map(role => html`
                                                <span key=${role.id} class="inline-block bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs mr-1">
                                                    ${role.name}
                                                </span>
                                            `)}
                                        </td>
                                        <td class="px-6 py-4 text-sm">${formatDate(user.last_login)}</td>
                                        <td class="px-6 py-4">
                                            <button
                                                class="text-blue-600 hover:text-blue-800 text-sm"
                                                onClick=${() => viewUserDetail(user.id)}
                                            >
                                                View Details
                                            </button>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                </div>
            `}

            ${activeTab === 'roles' && html`
                <div class="card">
                    <div class="p-6 border-b">
                        <h3 class="text-lg font-semibold">System Roles</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Role Name</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Permissions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-200">
                                ${roles.map(role => html`
                                    <tr key=${role.id}>
                                        <td class="px-6 py-4 font-medium">${role.name}</td>
                                        <td class="px-6 py-4 text-sm">${role.description}</td>
                                        <td class="px-6 py-4">
                                            <span class="${role.is_system_role ? 'bg-gray-100 text-gray-800' : 'bg-green-100 text-green-800'} px-2 py-1 rounded text-xs">
                                                ${role.is_system_role ? 'System' : 'Custom'}
                                            </span>
                                        </td>
                                        <td class="px-6 py-4 text-sm">${role.permission_count} permissions</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                </div>
            `}

            ${activeTab === 'sessions' && html`
                <div class="card">
                    <div class="p-6 border-b">
                        <h3 class="text-lg font-semibold">Active Sessions</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Session ID</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">IP Address</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Expires</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-200">
                                ${sessions.map(session => html`
                                    <tr key=${session.id}>
                                        <td class="px-6 py-4 font-medium">${session.username}</td>
                                        <td class="px-6 py-4 font-mono text-xs">${session.id.substring(0, 12)}...</td>
                                        <td class="px-6 py-4">${session.ip_address || 'Unknown'}</td>
                                        <td class="px-6 py-4 text-sm">${formatDate(session.created_at)}</td>
                                        <td class="px-6 py-4 text-sm">${formatDate(session.expires_at)}</td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                </div>
            `}
        </div>
    `;
}

// Audit Trail Page
function AuditPage() {
    const [events, setEvents] = useState([]);
    const [selectedEvent, setSelectedEvent] = useState(null);
    const [chainVerification, setChainVerification] = useState(null);
    const [loading, setLoading] = useState(true);
    const [filters, setFilters] = useState({
        event_type: '',
        user: '',
        entity_type: '',
        date_from: '',
        date_to: ''
    });

    useEffect(() => {
        loadEvents();
        verifyChain();
    }, []);

    const loadEvents = async () => {
        try {
            setLoading(true);
            const params = new URLSearchParams();
            Object.entries(filters).forEach(([key, value]) => {
                if (value) params.append(key, value);
            });
            
            const eventsRes = await api.get(`/api/audit?${params}`);
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

    const viewEventDetail = async (eventId) => {
        try {
            const eventDetail = await api.get(`/api/audit/${eventId}`);
            setSelectedEvent(eventDetail);
        } catch (error) {
            console.error('Failed to load event detail:', error);
        }
    };

    const applyFilters = () => {
        loadEvents();
    };

    if (selectedEvent) {
        return html`
            <div>
                <div class="flex items-center justify-between mb-6">
                    <h2 class="text-2xl font-bold text-gray-800">Audit Event Detail</h2>
                    <button
                        class="px-4 py-2 text-sm bg-gray-500 text-white rounded hover:bg-gray-600"
                        onClick=${() => setSelectedEvent(null)}
                    >
                        Back to Audit Trail
                    </button>
                </div>
                
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="card p-6">
                        <h3 class="text-lg font-semibold mb-4">Event Information</h3>
                        <div class="space-y-2">
                            <p><strong>Event ID:</strong> <span class="font-mono text-sm">${selectedEvent.event.id}</span></p>
                            <p><strong>Timestamp:</strong> ${formatDate(selectedEvent.event.timestamp)}</p>
                            <p><strong>Event Type:</strong> ${selectedEvent.event.event_type}</p>
                            <p><strong>Entity:</strong> ${selectedEvent.event.entity_type}/${selectedEvent.event.entity_id}</p>
                            <p><strong>User:</strong> ${selectedEvent.event.username}</p>
                            <p><strong>Description:</strong> ${selectedEvent.event.description}</p>
                        </div>
                    </div>
                    
                    <div class="card p-6">
                        <h3 class="text-lg font-semibold mb-4">Hash Chain Verification</h3>
                        <div class="space-y-2">
                            <p><strong>Current Hash:</strong></p>
                            <p class="font-mono text-xs bg-gray-100 p-2 rounded break-all">${selectedEvent.event.hash}</p>
                            <p><strong>Previous Hash:</strong></p>
                            <p class="font-mono text-xs bg-gray-100 p-2 rounded break-all">${selectedEvent.event.previous_hash || 'N/A (First event)'}</p>
                        </div>
                    </div>
                    
                    <div class="card p-6 lg:col-span-2">
                        <h3 class="text-lg font-semibold mb-4">Event Data</h3>
                        <pre class="bg-gray-100 p-4 rounded text-xs overflow-x-auto">${JSON.stringify(selectedEvent.event.data, null, 2)}</pre>
                    </div>
                </div>
            </div>
        `;
    }

    return html`
        <div>
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-2xl font-bold text-gray-800">Audit Trail</h2>
                <div class="flex items-center space-x-4">
                    ${chainVerification && html`
                        <div class="flex items-center space-x-2">
                            <span class="${chainVerification.chain_valid ? 'hash-chain-valid' : 'hash-chain-invalid'} font-medium">
                                Chain Status: ${chainVerification.chain_valid ? 'Valid' : 'Invalid'}
                            </span>
                            <div class="${chainVerification.chain_valid ? 'bg-green-500' : 'bg-red-500'} w-3 h-3 rounded-full"></div>
                        </div>
                    `}
                </div>
            </div>

            <div class="card mb-6">
                <div class="p-6">
                    <h3 class="text-lg font-semibold mb-4">Filters</h3>
                    <div class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
                        <input
                            type="text"
                            placeholder="Event Type"
                            class="px-3 py-2 border rounded-md text-sm"
                            value=${filters.event_type}
                            onChange=${e => setFilters({...filters, event_type: e.target.value})}
                        />
                        <input
                            type="text"
                            placeholder="User"
                            class="px-3 py-2 border rounded-md text-sm"
                            value=${filters.user}
                            onChange=${e => setFilters({...filters, user: e.target.value})}
                        />
                        <input
                            type="text"
                            placeholder="Entity Type"
                            class="px-3 py-2 border rounded-md text-sm"
                            value=${filters.entity_type}
                            onChange=${e => setFilters({...filters, entity_type: e.target.value})}
                        />
                        <input
                            type="date"
                            class="px-3 py-2 border rounded-md text-sm"
                            value=${filters.date_from}
                            onChange=${e => setFilters({...filters, date_from: e.target.value})}
                        />
                        <button
                            class="btn-primary px-4 py-2 text-white rounded-md text-sm hover:bg-blue-700"
                            onClick=${applyFilters}
                        >
                            Apply Filters
                        </button>
                    </div>
                </div>
            </div>

            ${loading ? html`<div class="text-center py-8">Loading audit events...</div>` : html`
                <div class="card">
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Timestamp</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Event Type</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Entity</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Hash</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-200">
                                ${events.map(event => html`
                                    <tr key=${event.id}>
                                        <td class="px-6 py-4 text-sm">${formatDate(event.timestamp)}</td>
                                        <td class="px-6 py-4">
                                            <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
                                                ${event.event_type}
                                            </span>
                                        </td>
                                        <td class="px-6 py-4 text-sm">${event.username}</td>
                                        <td class="px-6 py-4 text-sm">${event.entity_type}/${event.entity_id.substring(0, 8)}...</td>
                                        <td class="px-6 py-4 text-sm">${event.description}</td>
                                        <td class="px-6 py-4 font-mono text-xs">${event.hash.substring(0, 8)}...</td>
                                        <td class="px-6 py-4">
                                            <button
                                                class="text-blue-600 hover:text-blue-800 text-sm"
                                                onClick=${() => viewEventDetail(event.id)}
                                            >
                                                View Details
                                            </button>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                </div>
            `}
        </div>
    `;
}

// Workflows Page
function WorkflowsPage() {
    const [workflows, setWorkflows] = useState([]);
    const [definitions, setDefinitions] = useState([]);
    const [selectedWorkflow, setSelectedWorkflow] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('active');

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            setLoading(true);
            const [workflowsRes, definitionsRes] = await Promise.all([
                api.get('/api/workflows'),
                api.get('/api/workflows/definitions')
            ]);
            
            setWorkflows(workflowsRes.workflows);
            setDefinitions(definitionsRes.definitions);
        } catch (error) {
            console.error('Failed to load workflows:', error);
        } finally {
            setLoading(false);
        }
    };

    const viewWorkflowDetail = async (workflowId) => {
        try {
            const workflowDetail = await api.get(`/api/workflows/${workflowId}`);
            setSelectedWorkflow(workflowDetail);
        } catch (error) {
            console.error('Failed to load workflow detail:', error);
        }
    };

    const approveStep = async (workflowId, comments = '') => {
        try {
            await api.post(`/api/workflows/${workflowId}/approve`, {
                comments,
                user_id: 'current-user' // In real app, get from auth
            });
            
            // Reload workflow detail
            viewWorkflowDetail(workflowId);
            
            // Reload workflows list
            loadData();
        } catch (error) {
            console.error('Failed to approve step:', error);
            alert('Failed to approve step: ' + error.message);
        }
    };

    if (loading) return html`<div class="text-center py-8">Loading workflows...</div>`;

    if (selectedWorkflow) {
        const { workflow, steps, current_step_id } = selectedWorkflow;
        const currentStep = steps.find(s => s.id === current_step_id);

        return html`
            <div>
                <div class="flex items-center justify-between mb-6">
                    <h2 class="text-2xl font-bold text-gray-800">Workflow Detail</h2>
                    <button
                        class="px-4 py-2 text-sm bg-gray-500 text-white rounded hover:bg-gray-600"
                        onClick=${() => setSelectedWorkflow(null)}
                    >
                        Back to Workflows
                    </button>
                </div>
                
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div class="lg:col-span-2">
                        <div class="card p-6 mb-6">
                            <h3 class="text-lg font-semibold mb-4">Workflow Information</h3>
                            <div class="grid grid-cols-2 gap-4">
                                <div>
                                    <p><strong>Type:</strong> ${workflow.type}</p>
                                    <p><strong>Entity:</strong> ${workflow.entity_type}/${workflow.entity_id}</p>
                                    <p><strong>Status:</strong> 
                                        <span class="status-${workflow.status}">${workflow.status}</span>
                                    </p>
                                </div>
                                <div>
                                    <p><strong>Started:</strong> ${formatDate(workflow.created_at)}</p>
                                    <p><strong>SLA Deadline:</strong> ${formatDate(workflow.sla_deadline)}</p>
                                    <p><strong>Initiated By:</strong> ${workflow.initiated_by}</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="card p-6">
                            <h3 class="text-lg font-semibold mb-4">Step Timeline</h3>
                            <div class="space-y-4">
                                ${steps.map((step, index) => html`
                                    <div key=${step.id} class="flex items-start space-x-4">
                                        <div class="flex-shrink-0">
                                            <div class="${step.status === 'completed' ? 'bg-green-500' : step.status === 'in_progress' ? 'bg-blue-500' : 'bg-gray-300'} w-4 h-4 rounded-full"></div>
                                        </div>
                                        <div class="flex-1">
                                            <div class="flex items-center justify-between">
                                                <h4 class="font-medium">${step.name}</h4>
                                                <span class="status-${step.status} text-sm">${step.status}</span>
                                            </div>
                                            <p class="text-sm text-gray-600">${step.step_type}</p>
                                            <p class="text-xs text-gray-500">Created: ${formatDate(step.created_at)}</p>
                                            ${step.completed_at && html`
                                                <p class="text-xs text-gray-500">Completed: ${formatDate(step.completed_at)}</p>
                                            `}
                                            ${step.comments && html`
                                                <p class="text-sm mt-2 p-2 bg-gray-50 rounded">${step.comments}</p>
                                            `}
                                        </div>
                                    </div>
                                `)}
                            </div>
                        </div>
                    </div>
                    
                    <div class="space-y-6">
                        ${currentStep && currentStep.status === 'pending' && html`
                            <div class="card p-6">
                                <h3 class="text-lg font-semibold mb-4">Actions</h3>
                                <div class="space-y-4">
                                    <div>
                                        <label class="block text-sm font-medium mb-2">Comments</label>
                                        <textarea
                                            id="step-comments"
                                            rows="3"
                                            class="w-full px-3 py-2 border rounded-md text-sm"
                                            placeholder="Add comments for this approval..."
                                        ></textarea>
                                    </div>
                                    <button
                                        class="w-full btn-primary px-4 py-2 text-white rounded-md hover:bg-blue-700"
                                        onClick=${() => {
                                            const comments = document.getElementById('step-comments').value;
                                            approveStep(workflow.id, comments);
                                        }}
                                    >
                                        Approve Step
                                    </button>
                                </div>
                            </div>
                        `}
                        
                        <div class="card p-6">
                            <h3 class="text-lg font-semibold mb-4">Current Status</h3>
                            ${currentStep ? html`
                                <div class="space-y-2">
                                    <p><strong>Current Step:</strong> ${currentStep.name}</p>
                                    <p><strong>Assigned To:</strong> ${currentStep.assigned_to || 'Unassigned'}</p>
                                    <p><strong>Status:</strong> 
                                        <span class="status-${currentStep.status}">${currentStep.status}</span>
                                    </p>
                                </div>
                            ` : html`
                                <p class="text-gray-600">Workflow completed</p>
                            `}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    return html`
        <div>
            <h2 class="text-2xl font-bold text-gray-800 mb-6">Workflows</h2>
            
            <div class="mb-6">
                <nav class="flex space-x-1">
                    ${['active', 'definitions'].map(tab => html`
                        <button
                            key=${tab}
                            class="px-4 py-2 text-sm font-medium rounded-lg ${activeTab === tab ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:text-gray-700'}"
                            onClick=${() => setActiveTab(tab)}
                        >
                            ${tab === 'active' ? 'Active Workflows' : 'Workflow Definitions'}
                        </button>
                    `)}
                </nav>
            </div>

            ${activeTab === 'active' && html`
                <div class="card">
                    <div class="p-6 border-b">
                        <h3 class="text-lg font-semibold">Active Workflow Instances</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Entity</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Current Step</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">SLA Deadline</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-200">
                                ${workflows.map(workflow => html`
                                    <tr key=${workflow.id}>
                                        <td class="px-6 py-4">
                                            <span class="bg-purple-100 text-purple-800 px-2 py-1 rounded text-xs">
                                                ${workflow.type}
                                            </span>
                                        </td>
                                        <td class="px-6 py-4 text-sm">${workflow.entity_type}/${workflow.entity_id.substring(0, 8)}...</td>
                                        <td class="px-6 py-4">
                                            <span class="status-${workflow.status} font-medium">${workflow.status}</span>
                                        </td>
                                        <td class="px-6 py-4 text-sm">${workflow.current_step || 'N/A'}</td>
                                        <td class="px-6 py-4 text-sm">${formatDate(workflow.created_at)}</td>
                                        <td class="px-6 py-4 text-sm">${formatDate(workflow.sla_deadline)}</td>
                                        <td class="px-6 py-4">
                                            <button
                                                class="text-blue-600 hover:text-blue-800 text-sm"
                                                onClick=${() => viewWorkflowDetail(workflow.id)}
                                            >
                                                View Details
                                            </button>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                </div>
            `}

            ${activeTab === 'definitions' && html`
                <div class="card">
                    <div class="p-6 border-b">
                        <h3 class="text-lg font-semibold">Workflow Definitions</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Steps</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-200">
                                ${definitions.map(definition => html`
                                    <tr key=${definition.id}>
                                        <td class="px-6 py-4 font-medium">${definition.name}</td>
                                        <td class="px-6 py-4">
                                            <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
                                                ${definition.workflow_type}
                                            </span>
                                        </td>
                                        <td class="px-6 py-4 text-sm">${definition.description}</td>
                                        <td class="px-6 py-4 text-sm">${definition.step_count} steps</td>
                                        <td class="px-6 py-4">
                                            <span class="${definition.is_active ? 'text-green-600' : 'text-gray-500'} text-sm">
                                                ${definition.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                </div>
            `}
        </div>
    `;
}

// Notifications Page
function NotificationsPage() {
    const [notifications, setNotifications] = useState([]);
    const [templates, setTemplates] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('log');
    const [filters, setFilters] = useState({
        status: '',
        channel: '',
        type: ''
    });

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            setLoading(true);
            const [notificationsRes, templatesRes, statsRes] = await Promise.all([
                api.get('/api/notifications'),
                api.get('/api/notifications/templates'),
                api.get('/api/notifications/stats')
            ]);
            
            setNotifications(notificationsRes.notifications);
            setTemplates(templatesRes.templates);
            setStats(statsRes);
        } catch (error) {
            console.error('Failed to load notifications:', error);
        } finally {
            setLoading(false);
        }
    };

    const applyFilters = async () => {
        try {
            const params = new URLSearchParams();
            Object.entries(filters).forEach(([key, value]) => {
                if (value) params.append(key, value);
            });
            
            const notificationsRes = await api.get(`/api/notifications?${params}`);
            setNotifications(notificationsRes.notifications);
        } catch (error) {
            console.error('Failed to load filtered notifications:', error);
        }
    };

    if (loading) return html`<div class="text-center py-8">Loading notifications...</div>`;

    return html`
        <div>
            <h2 class="text-2xl font-bold text-gray-800 mb-6">Notifications</h2>
            
            ${stats && html`
                <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                    <div class="card p-4">
                        <div class="text-2xl font-bold text-green-600">${stats.sent || 0}</div>
                        <div class="text-sm text-gray-600">Sent</div>
                    </div>
                    <div class="card p-4">
                        <div class="text-2xl font-bold text-blue-600">${stats.delivered || 0}</div>
                        <div class="text-sm text-gray-600">Delivered</div>
                    </div>
                    <div class="card p-4">
                        <div class="text-2xl font-bold text-red-600">${stats.failed || 0}</div>
                        <div class="text-sm text-gray-600">Failed</div>
                    </div>
                    <div class="card p-4">
                        <div class="text-2xl font-bold text-gray-600">${stats.pending || 0}</div>
                        <div class="text-sm text-gray-600">Pending</div>
                    </div>
                </div>
            `}
            
            <div class="mb-6">
                <nav class="flex space-x-1">
                    ${['log', 'templates'].map(tab => html`
                        <button
                            key=${tab}
                            class="px-4 py-2 text-sm font-medium rounded-lg ${activeTab === tab ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:text-gray-700'}"
                            onClick=${() => setActiveTab(tab)}
                        >
                            ${tab === 'log' ? 'Notification Log' : 'Templates'}
                        </button>
                    `)}
                </nav>
            </div>

            ${activeTab === 'log' && html`
                <div>
                    <div class="card mb-6">
                        <div class="p-6">
                            <h3 class="text-lg font-semibold mb-4">Filters</h3>
                            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                                <select
                                    class="px-3 py-2 border rounded-md text-sm"
                                    value=${filters.status}
                                    onChange=${e => setFilters({...filters, status: e.target.value})}
                                >
                                    <option value="">All Statuses</option>
                                    <option value="sent">Sent</option>
                                    <option value="failed">Failed</option>
                                    <option value="pending">Pending</option>
                                </select>
                                <select
                                    class="px-3 py-2 border rounded-md text-sm"
                                    value=${filters.channel}
                                    onChange=${e => setFilters({...filters, channel: e.target.value})}
                                >
                                    <option value="">All Channels</option>
                                    <option value="email">Email</option>
                                    <option value="sms">SMS</option>
                                    <option value="push">Push</option>
                                    <option value="in_app">In App</option>
                                </select>
                                <select
                                    class="px-3 py-2 border rounded-md text-sm"
                                    value=${filters.type}
                                    onChange=${e => setFilters({...filters, type: e.target.value})}
                                >
                                    <option value="">All Types</option>
                                    <option value="transaction_alert">Transaction Alert</option>
                                    <option value="payment_reminder">Payment Reminder</option>
                                    <option value="workflow_update">Workflow Update</option>
                                    <option value="compliance_alert">Compliance Alert</option>
                                </select>
                                <button
                                    class="btn-primary px-4 py-2 text-white rounded-md text-sm hover:bg-blue-700"
                                    onClick=${applyFilters}
                                >
                                    Apply Filters
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="overflow-x-auto">
                            <table class="w-full">
                                <thead class="bg-gray-50">
                                    <tr>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Recipient</th>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Channel</th>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Subject</th>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Sent</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-gray-200">
                                    ${notifications.map(notification => html`
                                        <tr key=${notification.id}>
                                            <td class="px-6 py-4 text-sm">${notification.recipient}</td>
                                            <td class="px-6 py-4">
                                                <span class="bg-purple-100 text-purple-800 px-2 py-1 rounded text-xs">
                                                    ${notification.type}
                                                </span>
                                            </td>
                                            <td class="px-6 py-4">
                                                <span class="bg-gray-100 text-gray-800 px-2 py-1 rounded text-xs">
                                                    ${notification.channel}
                                                </span>
                                            </td>
                                            <td class="px-6 py-4">
                                                <span class="status-${notification.status} font-medium">
                                                    ${notification.status}
                                                </span>
                                            </td>
                                            <td class="px-6 py-4 text-sm">${notification.subject}</td>
                                            <td class="px-6 py-4 text-sm">${formatDate(notification.created_at)}</td>
                                            <td class="px-6 py-4 text-sm">${formatDate(notification.sent_at)}</td>
                                        </tr>
                                    `)}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            `}

            ${activeTab === 'templates' && html`
                <div class="card">
                    <div class="p-6 border-b">
                        <h3 class="text-lg font-semibold">Notification Templates</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Channel</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Subject</th>
                                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-200">
                                ${templates.map(template => html`
                                    <tr key=${template.id}>
                                        <td class="px-6 py-4 font-medium">${template.name}</td>
                                        <td class="px-6 py-4">
                                            <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
                                                ${template.type}
                                            </span>
                                        </td>
                                        <td class="px-6 py-4">
                                            <span class="bg-gray-100 text-gray-800 px-2 py-1 rounded text-xs">
                                                ${template.channel}
                                            </span>
                                        </td>
                                        <td class="px-6 py-4 text-sm">${template.subject}</td>
                                        <td class="px-6 py-4">
                                            <span class="${template.is_active ? 'text-green-600' : 'text-gray-500'} text-sm">
                                                ${template.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    </div>
                </div>
            `}
        </div>
    `;
}

// Compliance Page
function CompliancePage() {
    const [alerts, setAlerts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedAlert, setSelectedAlert] = useState(null);

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

    const viewAlertDetail = (alert) => {
        setSelectedAlert(alert);
    };

    if (loading) return html`<div class="text-center py-8">Loading compliance data...</div>`;

    const pendingAlerts = alerts.filter(a => a.status === 'pending');
    const resolvedAlerts = alerts.filter(a => a.status === 'resolved');

    if (selectedAlert) {
        return html`
            <div>
                <div class="flex items-center justify-between mb-6">
                    <h2 class="text-2xl font-bold text-gray-800">Compliance Alert Detail</h2>
                    <button
                        class="px-4 py-2 text-sm bg-gray-500 text-white rounded hover:bg-gray-600"
                        onClick=${() => setSelectedAlert(null)}
                    >
                        Back to Alerts
                    </button>
                </div>
                
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="card p-6">
                        <h3 class="text-lg font-semibold mb-4">Alert Information</h3>
                        <div class="space-y-2">
                            <p><strong>Alert ID:</strong> ${selectedAlert.id}</p>
                            <p><strong>Customer ID:</strong> ${selectedAlert.customer_id}</p>
                            <p><strong>Type:</strong> ${selectedAlert.alert_type}</p>
                            <p><strong>Severity:</strong> 
                                <span class="text-${selectedAlert.severity === 'high' ? 'red' : selectedAlert.severity === 'medium' ? 'yellow' : 'green'}-600 font-medium">
                                    ${selectedAlert.severity}
                                </span>
                            </p>
                            <p><strong>Status:</strong> 
                                <span class="status-${selectedAlert.status}">${selectedAlert.status}</span>
                            </p>
                            <p><strong>Risk Score:</strong> ${selectedAlert.risk_score}/100</p>
                            <p><strong>Created:</strong> ${formatDate(selectedAlert.created_at)}</p>
                            ${selectedAlert.resolved_at && html`
                                <p><strong>Resolved:</strong> ${formatDate(selectedAlert.resolved_at)}</p>
                            `}
                        </div>
                    </div>
                    
                    <div class="card p-6">
                        <h3 class="text-lg font-semibold mb-4">Description</h3>
                        <p class="text-sm">${selectedAlert.description}</p>
                    </div>
                </div>
            </div>
        `;
    }

    return html`
        <div>
            <h2 class="text-2xl font-bold text-gray-800 mb-6">Compliance</h2>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div class="card p-4">
                    <div class="text-2xl font-bold text-red-600">${pendingAlerts.length}</div>
                    <div class="text-sm text-gray-600">Pending Alerts</div>
                </div>
                <div class="card p-4">
                    <div class="text-2xl font-bold text-green-600">${resolvedAlerts.length}</div>
                    <div class="text-sm text-gray-600">Resolved Alerts</div>
                </div>
                <div class="card p-4">
                    <div class="text-2xl font-bold text-gray-600">${alerts.length}</div>
                    <div class="text-sm text-gray-600">Total Alerts</div>
                </div>
            </div>

            <div class="card">
                <div class="p-6 border-b">
                    <h3 class="text-lg font-semibold">Compliance Alerts</h3>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Customer ID</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Severity</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Risk Score</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200">
                            ${alerts.map(alert => html`
                                <tr key=${alert.id}>
                                    <td class="px-6 py-4 text-sm font-mono">${alert.customer_id.substring(0, 8)}...</td>
                                    <td class="px-6 py-4">
                                        <span class="bg-orange-100 text-orange-800 px-2 py-1 rounded text-xs">
                                            ${alert.alert_type}
                                        </span>
                                    </td>
                                    <td class="px-6 py-4">
                                        <span class="text-${alert.severity === 'high' ? 'red' : alert.severity === 'medium' ? 'yellow' : 'green'}-600 font-medium text-sm">
                                            ${alert.severity}
                                        </span>
                                    </td>
                                    <td class="px-6 py-4">
                                        <span class="status-${alert.status} font-medium">${alert.status}</span>
                                    </td>
                                    <td class="px-6 py-4 text-sm">${alert.risk_score}/100</td>
                                    <td class="px-6 py-4 text-sm">${formatDate(alert.created_at)}</td>
                                    <td class="px-6 py-4">
                                        <button
                                            class="text-blue-600 hover:text-blue-800 text-sm"
                                            onClick=${() => viewAlertDetail(alert)}
                                        >
                                            View Details
                                        </button>
                                    </td>
                                </tr>
                            `)}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

// Settings Page
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

    if (loading) return html`<div class="text-center py-8">Loading system settings...</div>`;

    return html`
        <div>
            <h2 class="text-2xl font-bold text-gray-800 mb-6">System Settings</h2>
            
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="card p-6">
                    <h3 class="text-lg font-semibold mb-4">Database</h3>
                    <div class="space-y-2">
                        <p><strong>Type:</strong> ${settings.database.type}</p>
                        <p><strong>Status:</strong> 
                            <span class="${settings.database.status === 'Connected' ? 'text-green-600' : 'text-red-600'}">
                                ${settings.database.status}
                            </span>
                        </p>
                        <p><strong>Size:</strong> ${settings.database.size_mb} MB</p>
                        <p><strong>Path:</strong> <span class="font-mono text-sm">${settings.database.path}</span></p>
                    </div>
                </div>
                
                <div class="card p-6">
                    <h3 class="text-lg font-semibold mb-4">Encryption</h3>
                    <div class="space-y-2">
                        <p><strong>Status:</strong> 
                            <span class="${settings.encryption.status === 'Enabled' ? 'text-green-600' : 'text-gray-600'}">
                                ${settings.encryption.status}
                            </span>
                        </p>
                        <p><strong>Algorithm:</strong> ${settings.encryption.algorithm}</p>
                    </div>
                </div>
                
                <div class="card p-6">
                    <h3 class="text-lg font-semibold mb-4">Kafka Integration</h3>
                    <div class="space-y-2">
                        <p><strong>Status:</strong> 
                            <span class="${settings.kafka.status === 'Connected' ? 'text-green-600' : 'text-gray-600'}">
                                ${settings.kafka.status}
                            </span>
                        </p>
                        <p><strong>Brokers:</strong> ${settings.kafka.brokers.length > 0 ? settings.kafka.brokers.join(', ') : 'None configured'}</p>
                    </div>
                </div>
                
                <div class="card p-6">
                    <h3 class="text-lg font-semibold mb-4">System Information</h3>
                    <div class="space-y-2">
                        <p><strong>Version:</strong> ${settings.system.version}</p>
                        <p><strong>Started:</strong> ${formatDate(settings.system.started_at)}</p>
                        <p><strong>Uptime:</strong> ${settings.system.uptime_hours} hours</p>
                    </div>
                </div>
                
                ${settings.tenancy && html`
                    <div class="card p-6 ${settings.tenancy.enabled ? 'lg:col-span-2' : ''}">
                        <h3 class="text-lg font-semibold mb-4">Multi-Tenancy</h3>
                        ${settings.tenancy.enabled ? html`
                            <div class="space-y-4">
                                <p><strong>Status:</strong> <span class="text-green-600">Enabled</span></p>
                                <p><strong>Total Tenants:</strong> ${settings.tenancy.tenant_count}</p>
                                
                                ${settings.tenancy.tenants.length > 0 && html`
                                    <div>
                                        <strong>Tenants:</strong>
                                        <div class="mt-2">
                                            <table class="w-full text-sm">
                                                <thead class="bg-gray-50">
                                                    <tr>
                                                        <th class="px-4 py-2 text-left">Name</th>
                                                        <th class="px-4 py-2 text-left">Status</th>
                                                        <th class="px-4 py-2 text-left">Created</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    ${settings.tenancy.tenants.map(tenant => html`
                                                        <tr key=${tenant.id} class="border-t">
                                                            <td class="px-4 py-2">${tenant.name}</td>
                                                            <td class="px-4 py-2">
                                                                <span class="${tenant.is_active ? 'text-green-600' : 'text-gray-500'}">
                                                                    ${tenant.is_active ? 'Active' : 'Inactive'}
                                                                </span>
                                                            </td>
                                                            <td class="px-4 py-2">${formatDate(tenant.created_at)}</td>
                                                        </tr>
                                                    `)}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                `}
                            </div>
                        ` : html`
                            <p><strong>Status:</strong> <span class="text-gray-600">Disabled</span></p>
                        `}
                    </div>
                `}
            </div>
        </div>
    `;
}

// Main App Component
function App() {
    const [currentPage, setCurrentPage] = useState('users');

    const renderPage = () => {
        switch (currentPage) {
            case 'users': return html`<${UsersPage} />`;
            case 'audit': return html`<${AuditPage} />`;
            case 'workflows': return html`<${WorkflowsPage} />`;
            case 'notifications': return html`<${NotificationsPage} />`;
            case 'compliance': return html`<${CompliancePage} />`;
            case 'settings': return html`<${SettingsPage} />`;
            default: return html`<${UsersPage} />`;
        }
    };

    return html`
        <div class="min-h-screen bg-gray-50">
            <${Sidebar} currentPage=${currentPage} onPageChange=${setCurrentPage} />
            <${MainContent}>
                ${renderPage()}
            <//>
        </div>
    `;
}

// Render the app
render(html`<${App} />`, document.getElementById('app'));