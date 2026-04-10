/* API Client for Smart Vision System */
const API_BASE = '';

class API {
    constructor() {
        this.token = localStorage.getItem('token');
    }

    getHeaders() {
        const headers = {
            'Content-Type': 'application/json'
        };
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        return headers;
    }

    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            ...options,
            headers: {
                ...this.getHeaders(),
                ...(options.headers || {})
            }
        };

        try {
            const response = await fetch(url, config);
            
            // Handle non-JSON responses
            let data;
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.includes("application/json")) {
                data = await response.json();
            } else {
                const text = await response.text();
                throw new Error(text || `HTTP ${response.status}`);
            }

            if (!response.ok) {
                const error = new Error(data.detail || data.message || 'Request failed');
                error.status = response.status;
                error.data = data;
                throw error;
            }

            return data;
        } catch (error) {
            // Network errors
            if (error instanceof TypeError) {
                throw new Error('Network error. Please check if the server is running.');
            }
            throw error;
        }
    }

    // Auth
    async register(userData) {
        return this.request('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify(userData)
        });
    }

    async login(credentials) {
        return this.request('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify(credentials)
        });
    }

    async getMe() {
        return this.request('/api/auth/me');
    }

    async updateMe(data) {
        // Filter out null values
        const filtered = Object.fromEntries(
            Object.entries(data).filter(([_, v]) => v !== null)
        );
        return this.request('/api/auth/me', {
            method: 'PUT',
            body: JSON.stringify(filtered)
        });
    }

    async changePassword(passwordData) {
        return this.request('/api/auth/change-password', {
            method: 'POST',
            body: JSON.stringify(passwordData)
        });
    }

    // Slots
    async getSlotsStatus(lotId) {
        const url = lotId != null ? '/api/slots/status?lot_id=' + lotId : '/api/slots/status';
        return this.request(url);
    }

    async getSlotStats(lotId) {
        const url = lotId != null ? '/api/slots/stats?lot_id=' + lotId : '/api/slots/stats';
        return this.request(url);
    }

    // Parking lots (for map)
    async getLots() {
        return this.request('/api/lots');
    }

    async getSlotsConfig(lotId) {
        const url = lotId != null ? '/api/slots/config?lot_id=' + lotId : '/api/slots/config';
        return this.request(url);
    }

    // Reservations
    async getMyReservations() {
        return this.request('/api/reservations/my-reservations');
    }

    async createReservation(reservationData) {
        return this.request('/api/reservations/create', {
            method: 'POST',
            body: JSON.stringify(reservationData)
        });
    }

    async confirmPayment(paymentData) {
        return this.request('/api/reservations/confirm-payment', {
            method: 'POST',
            body: JSON.stringify(paymentData)
        });
    }

    async cancelReservation(reservationId) {
        return this.request(`/api/reservations/${reservationId}/cancel`, {
            method: 'POST'
        });
    }

    // Payment methods
    async getPaymentMethods() {
        return this.request('/api/payments/methods');
    }

    async addPaymentMethod(data) {
        return this.request('/api/payments/methods', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async deletePaymentMethod(methodId) {
        return this.request(`/api/payments/methods/${methodId}`, {
            method: 'DELETE'
        });
    }

    async setDefaultPaymentMethod(methodId) {
        return this.request(`/api/payments/methods/${methodId}/default`, {
            method: 'PATCH'
        });
    }

    // Cars
    async getMyCars() {
        return this.request('/api/cars/');
    }

    async addCar(carData) {
        return this.request('/api/cars/', {
            method: 'POST',
            body: JSON.stringify(carData)
        });
    }

    async updateCar(carId, carData) {
        return this.request(`/api/cars/${carId}`, {
            method: 'PUT',
            body: JSON.stringify(carData)
        });
    }

    async deleteCar(carId) {
        return this.request(`/api/cars/${carId}`, {
            method: 'DELETE'
        });
    }

    // Admin
    async getAdminStats() {
        return this.request('/api/admin/stats');
    }

    async getAdminUsers() {
        return this.request('/api/admin/users');
    }

    async getAdminReservations() {
        return this.request('/api/admin/reservations');
    }

    async getAdminAnalyticsReservationsByDay(days) {
        return this.request('/api/admin/analytics/reservations-by-day?days=' + (days || 7));
    }

    async getAdminAnalyticsTopSlots(limit) {
        return this.request('/api/admin/analytics/top-slots?limit=' + (limit || 10));
    }

    async getAdminAuditLog(limit) {
        return this.request('/api/admin/audit-log?limit=' + (limit || 100));
    }

    async updateUserActive(userId, isActive) {
        return this.request('/api/admin/users/' + userId, {
            method: 'PATCH',
            body: JSON.stringify({ is_active: isActive })
        });
    }

    // Chat
    async chat(message) {
        return this.request('/api/chat/', {
            method: 'POST',
            body: JSON.stringify({ message: message })
        });
    }
}

const api = new API();
