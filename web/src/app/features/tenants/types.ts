export interface Tenant { id: string; name: string; enabled: boolean }
export interface Credential { id: string; api_key: string }
export interface Model { alias: string; enabled: boolean }
export interface Event { id: number; action: string; created_at: string; alias: string | null }
