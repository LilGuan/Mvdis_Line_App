import { today } from "../lib/formatters";

const dateOffset = (offset) => {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  return date.toISOString().split("T")[0];
};

export const seedRecords = [
  { id: 1001, type: "income", description: "FORCE 2.0 前後輪更換", amount: 3200, category: "維修費", record_date: today(), note: "阿明" },
  { id: 1002, type: "income", description: "JETS 125 排氣管改裝", amount: 8500, category: "改裝費", record_date: today(), note: "大頭" },
  { id: 1003, type: "expense", description: "馬吉斯輪胎進貨 x10", amount: 12000, category: "進貨", record_date: today(), note: "台灣馬吉斯" },
  { id: 1004, type: "income", description: "機油更換定期保養", amount: 1200, category: "維修費", record_date: dateOffset(-1), note: "小黑" },
  { id: 1005, type: "expense", description: "四月份店租", amount: 18000, category: "店租", record_date: dateOffset(-1), note: "" },
  { id: 1006, type: "income", description: "前叉 KYB 改裝", amount: 12000, category: "改裝費", record_date: dateOffset(-3), note: "阿明" },
  { id: 1007, type: "expense", description: "SP武川排氣管零件", amount: 7500, category: "進貨", record_date: dateOffset(-3), note: "" },
];

export const seedCustomers = [
  { id: 2001, name: "阿明", phone: "0912-345-678", bike: "FORCE 2.0", debt: 3200, note: "常來前叉改裝" },
  { id: 2002, name: "大頭", phone: "0923-456-789", bike: "JETS 125", debt: 0, note: "排氣管、ECU 客" },
  { id: 2003, name: "阿偉", phone: "0934-567-890", bike: "SMAX 155", debt: 8500, note: "全車改裝中" },
];

export const seedInventory = [
  { id: 3001, name: "馬吉斯輪胎 M6234 110/70-12", category: "輪胎", quantity: 6, cost: 850 },
  { id: 3002, name: "馬吉斯輪胎 BT601 120/70-13", category: "輪胎", quantity: 2, cost: 1200 },
  { id: 3003, name: "嘉實多機油 5W40 1L", category: "機油", quantity: 24, cost: 220 },
  { id: 3004, name: "SP武川 競技排氣管 JETS", category: "排氣管", quantity: 1, cost: 4800 },
];

export const seedAlerts = [
  { id: 4001, type: "danger", text: "阿偉全車改裝尾款 NT$8,500 尚未收款", sub: "請盡快聯絡確認付款方式" },
  { id: 4002, type: "warn", text: "馬吉斯輪胎 BT601 庫存僅剩 2 條", sub: "建議本週進貨補充" },
  { id: 4003, type: "info", text: "阿志訂單：AUGUR 155 坐墊訂製", sub: "零件已到，請安排施工時間" },
];
