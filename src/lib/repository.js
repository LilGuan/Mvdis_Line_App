import { hasSupabaseConfig, supabase } from "./supabaseClient";
import { localDb } from "./localStore";

const tableNames = {
  records: "records",
  customers: "customers",
  inventory: "inventory_items",
  alerts: "alerts",
};

const sortDesc = (rows) => [...rows].sort((a, b) => Number(b.id) - Number(a.id));

export async function loadBusinessData() {
  if (!hasSupabaseConfig) {
    return { ...localDb.loadAll(), source: "local" };
  }

  const [records, customers, inventory, alerts] = await Promise.all([
    supabase.from(tableNames.records).select("*").order("record_date", { ascending: false }),
    supabase.from(tableNames.customers).select("*").order("created_at", { ascending: false }),
    supabase.from(tableNames.inventory).select("*").order("created_at", { ascending: false }),
    supabase.from(tableNames.alerts).select("*").order("created_at", { ascending: false }),
  ]);

  const failed = [records, customers, inventory, alerts].find((res) => res.error);
  if (failed) throw failed.error;

  return {
    records: records.data ?? [],
    customers: customers.data ?? [],
    inventory: inventory.data ?? [],
    alerts: alerts.data ?? [],
    source: "supabase",
  };
}

export async function insertRow(table, row, currentRows) {
  if (!hasSupabaseConfig) {
    const rows = sortDesc([row, ...currentRows]);
    localDb.save(table, rows);
    return rows;
  }

  const { data, error } = await supabase.from(tableNames[table]).insert(row).select().single();
  if (error) throw error;
  return sortDesc([data, ...currentRows]);
}

export async function updateRows(table, rows) {
  if (!hasSupabaseConfig) {
    localDb.save(table, rows);
    return rows;
  }

  const { error } = await supabase.from(tableNames[table]).upsert(rows);
  if (error) throw error;
  return rows;
}

export async function deleteRow(table, id, currentRows) {
  const rows = currentRows.filter((row) => row.id !== id);
  if (!hasSupabaseConfig) {
    localDb.save(table, rows);
    return rows;
  }

  const { error } = await supabase.from(tableNames[table]).delete().eq("id", id);
  if (error) throw error;
  return rows;
}
