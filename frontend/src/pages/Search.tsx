import { useState } from 'react';
import { Search as SearchIcon, FileText } from 'lucide-react';
import { Card, Button, Input, Badge } from '../components/ui';

export function Search() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<null | Array<{
    document_id: string;
    text: string;
    score: number;
  }>>(null);
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    // Note: Search endpoint would need to be implemented in the API
    // For now, this is a placeholder
    setTimeout(() => {
      setResults([]);
      setIsSearching(false);
    }, 500);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Semantic Search</h1>
        <p className="text-sm text-gray-500 mt-1">
          Search across all documents using natural language
        </p>
      </div>

      <Card>
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="flex-1">
            <Input
              placeholder="Search for evidence, claims, or any content..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full"
            />
          </div>
          <Button type="submit" loading={isSearching}>
            <SearchIcon className="h-4 w-4" />
            Search
          </Button>
        </form>
      </Card>

      {results !== null && (
        <Card>
          {results.length === 0 ? (
            <div className="text-center py-8">
              <SearchIcon className="h-12 w-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">
                {query ? 'No results found' : 'Enter a search query to find documents'}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {results.map((result, index) => (
                <div
                  key={index}
                  className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-blue-600">
                        Document: {result.document_id.slice(0, 8)}...
                      </span>
                    </div>
                    <Badge variant="info">
                      Score: {(result.score * 100).toFixed(1)}%
                    </Badge>
                  </div>
                  <p className="text-gray-700">{result.text}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
