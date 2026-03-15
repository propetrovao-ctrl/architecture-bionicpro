import React, { useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';

interface ReportRow {
  user_id: string;
  period_from: string;
  period_to: string;
  full_name: string | null;
  email: string | null;
  total_usage_mins: number;
  total_events: number;
  updated_at: string;
}

interface ReportResponse {
  user_id: string;
  reports: ReportRow[];
  message?: string;
}

const ReportPage: React.FC = () => {
  const { keycloak, initialized } = useKeycloak();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);

  const fetchReport = async () => {
    if (!keycloak?.token) {
      setError('Not authenticated');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setReport(null);

      const response = await fetch(`${process.env.REACT_APP_API_URL}/reports`, {
        headers: {
          Authorization: `Bearer ${keycloak.token}`,
        },
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const message = data.detail || response.statusText;
        if (response.status === 401) throw new Error('Not authenticated');
        if (response.status === 403) throw new Error('Access denied');
        if (response.status === 404) throw new Error('No report for this period yet.');
        throw new Error(message);
      }

      const data: ReportResponse = await response.json();
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  if (!initialized) {
    return <div>Loading...</div>;
  }

  if (!keycloak.authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={() => keycloak.login()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md max-w-2xl w-full">
        <h1 className="text-2xl font-bold mb-6">Usage Reports</h1>

        <button
          onClick={fetchReport}
          disabled={loading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Loading...' : 'Get my report'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">
            {error}
          </div>
        )}

        {report && (
          <div className="mt-6">
            <h2 className="text-lg font-semibold mb-2">Report for {report.user_id}</h2>
            <div className="overflow-x-auto">
              <table className="min-w-full border border-gray-300">
                <thead>
                  <tr className="bg-gray-200">
                    <th className="border px-2 py-1 text-left">Period</th>
                    <th className="border px-2 py-1 text-left">Usage (min)</th>
                    <th className="border px-2 py-1 text-left">Events</th>
                  </tr>
                </thead>
                <tbody>
                  {report.reports.map((r, i) => (
                    <tr key={i}>
                      <td className="border px-2 py-1">{r.period_from} — {r.period_to}</td>
                      <td className="border px-2 py-1">{r.total_usage_mins}</td>
                      <td className="border px-2 py-1">{r.total_events}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;