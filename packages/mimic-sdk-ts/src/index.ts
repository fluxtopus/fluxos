import axios, { AxiosInstance } from 'axios';

export interface SendNotificationRequest {
  recipient: string;
  content: string;
  provider: string;
  template_id?: string;
  metadata?: Record<string, any>;
}

export interface DeliveryStatus {
  delivery_id: string;
  status: string;
  provider: string;
  recipient: string;
  sent_at?: string;
  completed_at?: string;
  error_message?: string;
}

export interface ProviderKey {
  id: string;
  provider_type: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export class MimicClient {
  private client: AxiosInstance;

  constructor(apiKey: string, baseUrl: string = 'http://localhost:8000') {
    this.client = axios.create({
      baseURL: baseUrl,
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });
  }

  async sendNotification(request: SendNotificationRequest): Promise<{ delivery_id: string; status: string; message: string }> {
    const response = await this.client.post('/api/v1/send', request);
    return response.data;
  }

  async getDeliveryStatus(deliveryId: string): Promise<DeliveryStatus> {
    const response = await this.client.get(`/api/v1/status/${deliveryId}`);
    return response.data;
  }

  async createProviderKey(providerType: string, credentials: {
    api_key?: string;
    secret?: string;
    webhook_url?: string;
    bot_token?: string;
    from_email?: string;
    from_number?: string;
  }): Promise<ProviderKey> {
    const response = await this.client.post('/api/v1/provider-keys', {
      provider_type: providerType,
      ...credentials
    });
    return response.data;
  }

  async listProviderKeys(): Promise<ProviderKey[]> {
    const response = await this.client.get('/api/v1/provider-keys');
    return response.data;
  }

  async testProviderKey(providerType: string): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post(`/api/v1/provider-keys/${providerType}/test`);
    return response.data;
  }

  async createTemplate(name: string, content: string, variables?: string[]): Promise<any> {
    const response = await this.client.post('/api/v1/templates', {
      name,
      content,
      variables
    });
    return response.data;
  }

  async listTemplates(): Promise<any[]> {
    const response = await this.client.get('/api/v1/templates');
    return response.data;
  }

  async getDeliveryLogs(options?: {
    limit?: number;
    offset?: number;
    provider?: string;
    status?: string;
  }): Promise<any[]> {
    const response = await this.client.get('/api/v1/logs', { params: options });
    return response.data;
  }

  async getAnalytics(days: number = 30): Promise<any> {
    const response = await this.client.get('/api/v1/analytics', { params: { days } });
    return response.data;
  }
}

