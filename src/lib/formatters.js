export const today = () => new Date().toISOString().split("T")[0];

export const currentMonth = () => today().slice(0, 7);

export const money = (value = 0) =>
  `NT$${Math.round(Math.abs(Number(value) || 0)).toLocaleString("zh-TW")}`;

export const signedMoney = (value = 0) => `${Number(value) >= 0 ? "+" : "-"}${money(value)}`;

export const newId = () => Date.now() + Math.floor(Math.random() * 1000);
