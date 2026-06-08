/**
 * Sample email receipts for testing receipt parser
 */

const uberEatsReceipt = {
  from: 'uber.us@uber.com',
  subject: 'Your Uber Eats receipt',
  body: `
Hi there,

Thanks for your order!

Order from: Chipotle Mexican Grill
Monday, June 6, 2026 7:15 PM

Items:
Burrito Bowl (Chicken) x1 - $11.50
Chips & Guacamole x1 - $3.00

Subtotal: $14.50
Delivery: $0.00
Service Fee: $1.50
Tip: $2.50

Order total: $18.50

Thanks for using Uber Eats!
  `.trim()
};

const doorDashReceipt = {
  from: 'no-reply@doordash.com',
  subject: 'Your DoorDash Receipt',
  body: `
Your DoorDash order

Sweetgreen
123 Main St

Order Details:
Harvest Bowl $14.25
Lemonade $3.50

Subtotal: $17.75
Delivery Fee: $2.99
Service Fee: $2.00
Tip: $3.50

Total: $26.24

Delivered on June 6, 2026 at 12:30 PM
  `.trim()
};

const grubhubReceipt = {
  from: 'orders@grubhub.com',
  subject: 'Your Grubhub order from Panera Bread',
  body: `
Your order from Panera Bread

Order placed: 06/06/2026 1:45 PM

Items:
1x Mediterranean Veggie Sandwich $10.99
1x Caesar Salad $8.49
2x Fountain Drink $2.99

Subtotal: $25.46
Delivery: $3.99
Tax: $2.29
Tip: $4.00

Total: $35.74

Thank you for your order!
  `.trim()
};

const multiItemReceipt = {
  from: 'uber.us@uber.com',
  subject: 'Your Uber Eats receipt',
  body: `
Order from: Panda Express
Tuesday, June 7, 2026 8:30 PM

Items:
Orange Chicken Bowl x2 - $9.50
Beijing Beef x1 - $10.25
Chow Mein (Large) x1 - $4.50
Spring Rolls (4 pack) x1 - $3.75

Subtotal: $37.50
Delivery: $0.00
Tip: $5.00

Order total: $42.50
  `.trim()
};

const invalidReceipt = {
  from: 'noreply@amazon.com',
  subject: 'Your Amazon order has shipped',
  body: `
Your Amazon package is on the way!

Order #123-4567890-1234567

Item: Wireless Mouse
Price: $29.99

Estimated delivery: June 10, 2026
  `.trim()
};

const uberEatsPdfOnlyReceipt = {
  from: 'Uber Receipts <noreply@uber.com>',
  subject: 'Uber Receipts',
  body: `
Thanks for ordering, Duo

Here's your receipt for Walmart (9251 Alderbridge Way, Richmond).

Total CA$56.86

To view your full receipt go to Uber Eats, or download this PDF

CA$7.58
Uber One savings and other promotions applied

Payments
Visa ****2906
6/7/26 8:28 AM
CA$56.86
  `.trim()
};

module.exports = {
  uberEatsReceipt,
  doorDashReceipt,
  grubhubReceipt,
  multiItemReceipt,
  invalidReceipt,
  uberEatsPdfOnlyReceipt
};
