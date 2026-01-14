import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Key,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { format } from 'date-fns';
import {
  Card,
  CardTitle,
  CardDescription,
  Button,
  Input,
  Textarea,
  Select,
  Badge,
  Modal,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/ui';
import { adminApi } from '../api';
import type {
  IntegrationKeyCreate,
  IntegrationProvider,
  IntegrationStatus,
} from '../types';

const providerOptions = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'lovepdf', label: 'LovePDF' },
  { value: 'aws', label: 'AWS' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'custom', label: 'Custom' },
];

const keyTypesByProvider: Record<string, { value: string; label: string }[]> = {
  openai: [{ value: 'api_key', label: 'API Key' }],
  lovepdf: [
    { value: 'public_key', label: 'Public Key' },
    { value: 'secret_key', label: 'Secret Key' },
  ],
  aws: [
    { value: 'access_key_id', label: 'Access Key ID' },
    { value: 'secret_access_key', label: 'Secret Access Key' },
  ],
  anthropic: [{ value: 'api_key', label: 'API Key' }],
  custom: [{ value: 'api_key', label: 'API Key' }],
};

function IntegrationCard({
  name,
  status,
  onTest,
  isTesting,
}: {
  name: string;
  status: IntegrationStatus;
  onTest: () => void;
  isTesting: boolean;
}) {
  const getStatusIcon = () => {
    if (status.configured) {
      return <CheckCircle className="h-6 w-6 text-green-500" />;
    }
    if (status.missing_key_types.length > 0) {
      return <AlertTriangle className="h-6 w-6 text-yellow-500" />;
    }
    return <XCircle className="h-6 w-6 text-gray-400" />;
  };

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          {getStatusIcon()}
          <div>
            <h3 className="font-semibold text-gray-900">{name}</h3>
            <p className="text-sm text-gray-500 mt-1">
              {status.configured ? (
                <span className="text-green-600">Configured</span>
              ) : status.missing_key_types.length > 0 ? (
                <span className="text-yellow-600">
                  Missing: {status.missing_key_types.join(', ')}
                </span>
              ) : (
                <span className="text-gray-500">Not configured</span>
              )}
            </p>
            <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
              <span>{status.active_keys_count} active keys</span>
              {status.last_used && (
                <span>Last used: {format(new Date(status.last_used), 'PP')}</span>
              )}
            </div>
          </div>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={onTest}
          loading={isTesting}
          disabled={!status.configured}
        >
          <RefreshCw className="h-4 w-4" />
          Test
        </Button>
      </div>
    </Card>
  );
}

export function Settings() {
  const queryClient = useQueryClient();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [revealedKeyId, setRevealedKeyId] = useState<string | null>(null);
  const [testingProvider, setTestingProvider] = useState<IntegrationProvider | null>(null);
  const [formData, setFormData] = useState<IntegrationKeyCreate>({
    provider: 'openai',
    name: '',
    key_type: 'api_key',
    value: '',
    description: '',
  });

  const { data: status } = useQuery({
    queryKey: ['integration-status'],
    queryFn: adminApi.getIntegrationStatus,
  });

  const { data: keys } = useQuery({
    queryKey: ['integration-keys'],
    queryFn: () => adminApi.listKeys(),
  });

  const { data: revealedKey } = useQuery({
    queryKey: ['integration-key-reveal', revealedKeyId],
    queryFn: () => (revealedKeyId ? adminApi.revealKey(revealedKeyId) : null),
    enabled: !!revealedKeyId,
  });

  const createMutation = useMutation({
    mutationFn: (data: IntegrationKeyCreate) => adminApi.createKey(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integration-keys'] });
      queryClient.invalidateQueries({ queryKey: ['integration-status'] });
      setCreateModalOpen(false);
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => adminApi.deleteKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integration-keys'] });
      queryClient.invalidateQueries({ queryKey: ['integration-status'] });
    },
  });

  const testMutation = useMutation({
    mutationFn: (provider: IntegrationProvider) => adminApi.testIntegration(provider),
    onSettled: () => {
      setTestingProvider(null);
    },
  });

  const resetForm = () => {
    setFormData({
      provider: 'openai',
      name: '',
      key_type: 'api_key',
      value: '',
      description: '',
    });
  };

  const handleProviderChange = (provider: IntegrationProvider) => {
    const keyTypes = keyTypesByProvider[provider] || [];
    setFormData({
      ...formData,
      provider,
      key_type: keyTypes[0]?.value || 'api_key',
    });
  };

  const handleTest = (provider: IntegrationProvider) => {
    setTestingProvider(provider);
    testMutation.mutate(provider);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(formData);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage third-party integrations and API keys
          </p>
        </div>
        <Button onClick={() => setCreateModalOpen(true)}>
          <Plus className="h-4 w-4" />
          Add API Key
        </Button>
      </div>

      {/* Integration Status Cards */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Integrations</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {status && (
            <>
              <IntegrationCard
                name="OpenAI"
                status={status.openai}
                onTest={() => handleTest('openai')}
                isTesting={testingProvider === 'openai'}
              />
              <IntegrationCard
                name="LovePDF"
                status={status.lovepdf}
                onTest={() => handleTest('lovepdf')}
                isTesting={testingProvider === 'lovepdf'}
              />
              <IntegrationCard
                name="AWS S3"
                status={status.aws}
                onTest={() => handleTest('aws')}
                isTesting={testingProvider === 'aws'}
              />
            </>
          )}
        </div>
      </div>

      {/* Test Result */}
      {testMutation.data && (
        <Card
          className={
            testMutation.data.success
              ? 'border-green-200 bg-green-50'
              : 'border-red-200 bg-red-50'
          }
        >
          <div className="flex items-center gap-3">
            {testMutation.data.success ? (
              <CheckCircle className="h-5 w-5 text-green-500" />
            ) : (
              <XCircle className="h-5 w-5 text-red-500" />
            )}
            <div>
              <p className="font-medium text-gray-900">
                {testMutation.data.provider.toUpperCase()} Test{' '}
                {testMutation.data.success ? 'Passed' : 'Failed'}
              </p>
              <p className="text-sm text-gray-600">{testMutation.data.message}</p>
            </div>
          </div>
        </Card>
      )}

      {/* API Keys Table */}
      <Card padding="none">
        <div className="p-6 border-b border-gray-200">
          <CardTitle>API Keys</CardTitle>
          <CardDescription>
            Manage your third-party API keys. Keys are encrypted at rest.
          </CardDescription>
        </div>

        {!keys?.items.length ? (
          <div className="p-8 text-center">
            <Key className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">No API keys configured</p>
            <Button
              variant="secondary"
              className="mt-4"
              onClick={() => setCreateModalOpen(true)}
            >
              Add your first key
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.items.map((key) => (
                <TableRow key={key.id}>
                  <TableCell>
                    <Badge variant="info">{key.provider}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className="font-medium">{key.name}</span>
                  </TableCell>
                  <TableCell>
                    <span className="text-gray-500">{key.key_type}</span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <code className="text-sm bg-gray-100 px-2 py-1 rounded">
                        {revealedKeyId === key.id && revealedKey
                          ? revealedKey.decrypted_value
                          : key.masked_value}
                      </code>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setRevealedKeyId(revealedKeyId === key.id ? null : key.id)
                        }
                      >
                        {revealedKeyId === key.id ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={key.is_active ? 'success' : 'default'}>
                      {key.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {format(new Date(key.created_at), 'MMM d, yyyy')}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (confirm('Are you sure you want to delete this key?')) {
                          deleteMutation.mutate(key.id);
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Create Key Modal */}
      <Modal
        isOpen={createModalOpen}
        onClose={() => {
          setCreateModalOpen(false);
          resetForm();
        }}
        title="Add API Key"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <Select
            label="Provider"
            options={providerOptions}
            value={formData.provider}
            onChange={(e) => handleProviderChange(e.target.value as IntegrationProvider)}
          />
          <Select
            label="Key Type"
            options={keyTypesByProvider[formData.provider] || []}
            value={formData.key_type}
            onChange={(e) => setFormData({ ...formData, key_type: e.target.value })}
          />
          <Input
            label="Name"
            placeholder="e.g., Production OpenAI Key"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            required
          />
          <Input
            label="API Key Value"
            type="password"
            placeholder="Enter your API key"
            value={formData.value}
            onChange={(e) => setFormData({ ...formData, value: e.target.value })}
            required
          />
          <Textarea
            label="Description (optional)"
            placeholder="Optional description..."
            rows={2}
            value={formData.description || ''}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
          />
          <div className="flex justify-end gap-3 pt-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setCreateModalOpen(false);
                resetForm();
              }}
            >
              Cancel
            </Button>
            <Button type="submit" loading={createMutation.isPending}>
              Add Key
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
