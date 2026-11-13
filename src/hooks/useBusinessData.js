import { useCallback, useEffect, useMemo, useState } from "react";
import { newId, today } from "../lib/formatters";
import { deleteRow, insertRow, loadBusinessData, updateRows } from "../lib/repository";

export function useBusinessData() {
  const [records, setRecords] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [source, setSource] = useState("loading");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const notify = useCallback((text) => setMessage(text), []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await loadBusinessData();
      setRecords(data.records);
      setCustomers(data.customers);
      setInventory(data.inventory);
      setAlerts(data.alerts);
      setSource(data.source);
    } catch (error) {
      notify(`Supabase 讀取失敗：${error.message}`);
      setSource("error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const api = useMemo(() => ({
    async addRecord(input) {
      const row = { id: newId(), ...input };
      const rows = await insertRow("records", row, records);
      setRecords(rows);
      notify(`已新增${row.type === "income" ? "收入" : "支出"}`);
    },
    async removeRecord(id) {
      const rows = await deleteRow("records", id, records);
      setRecords(rows);
      notify("已刪除記錄");
    },
    async addCustomer(input) {
      const row = { id: newId(), ...input };
      const rows = await insertRow("customers", row, customers);
      setCustomers(rows);
      notify(`已新增常客：${row.name}`);
    },
    async updateCustomerDebt(id, delta, amount) {
      const rows = customers.map((customer) =>
        customer.id === id ? { ...customer, debt: Math.max(0, Number(customer.debt) + delta * amount) } : customer,
      );
      await updateRows("customers", rows);
      setCustomers(rows);
      notify(delta > 0 ? "已新增欠款" : "已記錄還款");
    },
    async removeCustomer(id) {
      const rows = await deleteRow("customers", id, customers);
      setCustomers(rows);
      notify("已刪除常客");
    },
    async addInventoryItem(input) {
      const row = { id: newId(), ...input };
      const rows = await insertRow("inventory", row, inventory);
      setInventory(rows);
      notify("已新增零件");
    },
    async updateInventoryQty(id, delta) {
      const rows = inventory.map((item) =>
        item.id === id ? { ...item, quantity: Math.max(0, Number(item.quantity) + delta) } : item,
      );
      await updateRows("inventory", rows);
      setInventory(rows);
    },
    async removeInventoryItem(id) {
      const rows = await deleteRow("inventory", id, inventory);
      setInventory(rows);
      notify("已刪除零件");
    },
    async addAlert(text, type) {
      const row = { id: newId(), type, text, sub: `手動新增 · ${today()}` };
      const rows = await insertRow("alerts", row, alerts);
      setAlerts(rows);
      notify("已新增提醒");
    },
    async removeAlert(id) {
      const rows = await deleteRow("alerts", id, alerts);
      setAlerts(rows);
      notify("已刪除提醒");
    },
  }), [alerts, customers, inventory, notify, records]);

  return {
    records,
    customers,
    inventory,
    alerts,
    source,
    loading,
    message,
    clearMessage: () => setMessage(""),
    refresh,
    ...api,
  };
}
