export const log = (message) => {
  console.log(`[${new Date().toISOString()}] ${message}`);
};

export const error = (message) => {
  console.error(`[ERROR ${new Date().toISOString()}] ${message}`);
};
