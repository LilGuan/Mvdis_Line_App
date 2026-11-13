import { useState } from "react";
import Sidebar from "./components/layout/Sidebar";
import Topbar from "./components/layout/Topbar";
import Toast from "./components/ui/Toast";
import AlertsPage from "./features/alerts/AlertsPage";
import CustomersPage from "./features/customers/CustomersPage";
import DashboardPage from "./features/dashboard/DashboardPage";
import HistoryPage from "./features/history/HistoryPage";
import InventoryPage from "./features/inventory/InventoryPage";
import InvoicePage from "./features/invoice/InvoicePage";
import RecordsPage from "./features/records/RecordsPage";
import TaxPage from "./features/tax/TaxPage";
import { useBusinessData } from "./hooks/useBusinessData";

export default function App() {
  const [page, setPage] = useState("dashboard");
  const data = useBusinessData();

  const pageProps = {
    records: data.records,
    customers: data.customers,
    inventory: data.inventory,
    alerts: data.alerts,
    onAddRecord: data.addRecord,
    onDeleteRecord: data.removeRecord,
    onAddCustomer: data.addCustomer,
    onDebtChange: data.updateCustomerDebt,
    onDeleteCustomer: data.removeCustomer,
    onAddItem: data.addInventoryItem,
    onUpdateQty: data.updateInventoryQty,
    onDeleteItem: data.removeInventoryItem,
    onAddAlert: data.addAlert,
    onDeleteAlert: data.removeAlert,
  };

  return (
    <>
      <Topbar alertCount={data.alerts.length} source={data.source} onAlerts={() => setPage("alerts")} />
      <div className="layout">
        <Sidebar activePage={page} onChange={setPage} />
        <main className="main">
          {data.loading && <div className="empty loading">// 資料載入中</div>}
          {!data.loading && page === "dashboard" && <DashboardPage {...pageProps} />}
          {!data.loading && page === "income" && <RecordsPage type="income" {...pageProps} />}
          {!data.loading && page === "expense" && <RecordsPage type="expense" {...pageProps} />}
          {!data.loading && page === "customers" && <CustomersPage {...pageProps} />}
          {!data.loading && page === "inventory" && <InventoryPage {...pageProps} />}
          {!data.loading && page === "invoice" && <InvoicePage customers={data.customers} />}
          {!data.loading && page === "tax" && <TaxPage records={data.records} />}
          {!data.loading && page === "history" && <HistoryPage {...pageProps} />}
          {!data.loading && page === "alerts" && <AlertsPage {...pageProps} />}
        </main>
      </div>
      <Toast message={data.message} onDone={data.clearMessage} />
    </>
  );
}
