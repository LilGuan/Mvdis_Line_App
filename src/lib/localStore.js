import { seedAlerts, seedCustomers, seedInventory, seedRecords } from "../data/seed";

const keys = {
  records: "999r_records",
  customers: "999r_customers",
  inventory: "999r_inventory",
  alerts: "999r_alerts",
  seeded: "999r_react_seeded",
};

const read = (key, fallback) => {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch {
    return fallback;
  }
};

const write = (key, value) => localStorage.setItem(key, JSON.stringify(value));

export const ensureLocalSeed = () => {
  if (localStorage.getItem(keys.seeded)) return;
  write(keys.records, seedRecords);
  write(keys.customers, seedCustomers);
  write(keys.inventory, seedInventory);
  write(keys.alerts, seedAlerts);
  localStorage.setItem(keys.seeded, "1");
};

export const localDb = {
  loadAll() {
    ensureLocalSeed();
    return {
      records: read(keys.records, []),
      customers: read(keys.customers, []),
      inventory: read(keys.inventory, []),
      alerts: read(keys.alerts, []),
    };
  },
  save(table, rows) {
    write(keys[table], rows);
  },
};
