const {
  parseDeliveryReceipt,
  detectPlatform,
  extractRestaurant,
  extractItems,
  extractTotal,
  isPdfOnlyReceipt
} = require('../src/fetchers/receiptParser');

const {
  uberEatsReceipt,
  doorDashReceipt,
  grubhubReceipt,
  multiItemReceipt,
  invalidReceipt,
  uberEatsPdfOnlyReceipt
} = require('./fixtures/sampleReceipts');

describe('Receipt Parser', () => {
  describe('detectPlatform', () => {
    it('should detect UberEats from email', () => {
      expect(detectPlatform(uberEatsReceipt)).toBe('UberEats');
    });

    it('should detect DoorDash from email', () => {
      expect(detectPlatform(doorDashReceipt)).toBe('DoorDash');
    });

    it('should detect Grubhub from email', () => {
      expect(detectPlatform(grubhubReceipt)).toBe('Grubhub');
    });

    it('should return null for non-delivery emails', () => {
      expect(detectPlatform(invalidReceipt)).toBeNull();
    });
  });

  describe('extractRestaurant', () => {
    it('should extract restaurant from UberEats receipt', () => {
      const restaurant = extractRestaurant(uberEatsReceipt.body, 'UberEats');
      expect(restaurant).toBe('Chipotle Mexican Grill');
    });

    it('should extract restaurant from DoorDash receipt', () => {
      const restaurant = extractRestaurant(doorDashReceipt.body, 'DoorDash');
      expect(restaurant).toBe('Sweetgreen');
    });

    it('should extract restaurant from Grubhub receipt', () => {
      const restaurant = extractRestaurant(grubhubReceipt.body, 'Grubhub');
      expect(restaurant).toBe('Panera Bread');
    });
  });

  describe('extractItems', () => {
    it('should extract items from UberEats receipt', () => {
      const items = extractItems(uberEatsReceipt.body, 'UberEats');

      expect(items).toHaveLength(2);
      expect(items[0]).toMatchObject({
        name: 'Burrito Bowl (Chicken)',
        quantity: 1,
        price: 11.50
      });
      expect(items[1]).toMatchObject({
        name: 'Chips & Guacamole',
        quantity: 1,
        price: 3.00
      });
    });

    it('should extract items from DoorDash receipt', () => {
      const items = extractItems(doorDashReceipt.body, 'DoorDash');

      expect(items.length).toBeGreaterThan(0);
      expect(items.some(item => item.name.includes('Harvest Bowl'))).toBe(true);
    });

    it('should extract items with different quantity formats', () => {
      const items = extractItems(grubhubReceipt.body, 'Grubhub');

      expect(items.length).toBeGreaterThan(0);
      const drinkItem = items.find(item => item.name.includes('Fountain Drink'));
      if (drinkItem) {
        expect(drinkItem.quantity).toBe(2);
      }
    });

    it('should handle multiple items correctly', () => {
      const items = extractItems(multiItemReceipt.body, 'UberEats');

      expect(items.length).toBeGreaterThanOrEqual(2);
      const orangeChicken = items.find(item => item.name.includes('Orange Chicken'));
      if (orangeChicken) {
        expect(orangeChicken.quantity).toBe(2);
      }
    });
  });

  describe('extractTotal', () => {
    it('should extract total from UberEats receipt', () => {
      const total = extractTotal(uberEatsReceipt.body);
      expect(total).toBe(18.50);
    });

    it('should extract total from DoorDash receipt', () => {
      const total = extractTotal(doorDashReceipt.body);
      expect(total).toBe(26.24);
    });

    it('should extract total from Grubhub receipt', () => {
      const total = extractTotal(grubhubReceipt.body);
      expect(total).toBe(35.74);
    });
  });

  describe('parseDeliveryReceipt (integration)', () => {
    it('should parse complete UberEats receipt', async () => {
      const result = await parseDeliveryReceipt(uberEatsReceipt);

      expect(result).not.toBeNull();
      expect(result.platform).toBe('UberEats');
      expect(result.restaurant).toBe('Chipotle Mexican Grill');
      expect(result.items).toHaveLength(2);
      expect(result.total).toBe(18.50);
      expect(result.timestamp).toBeDefined();
    });

    it('should parse complete DoorDash receipt', async () => {
      const result = await parseDeliveryReceipt(doorDashReceipt);

      expect(result).not.toBeNull();
      expect(result.platform).toBe('DoorDash');
      expect(result.restaurant).toBe('Sweetgreen');
      expect(result.items.length).toBeGreaterThan(0);
      expect(result.total).toBe(26.24);
    });

    it('should return null for invalid receipts', async () => {
      const result = await parseDeliveryReceipt(invalidReceipt);
      expect(result).toBeNull();
    });

    it('should include raw email data', async () => {
      const result = await parseDeliveryReceipt(uberEatsReceipt);

      expect(result.raw).toBeDefined();
      expect(result.raw.from).toBe(uberEatsReceipt.from);
      expect(result.raw.subject).toBe(uberEatsReceipt.subject);
    });
  });

  describe('PDF-only receipts', () => {
    it('should detect PDF-only receipts', () => {
      expect(isPdfOnlyReceipt(uberEatsPdfOnlyReceipt.body)).toBe(true);
      expect(isPdfOnlyReceipt(uberEatsReceipt.body)).toBe(false);
    });

    it('should parse PDF-only receipt with warning', async () => {
      const result = await parseDeliveryReceipt(uberEatsPdfOnlyReceipt);

      expect(result).not.toBeNull();
      expect(result.platform).toBe('UberEats');
      expect(result.restaurant).toBe('Walmart');
      expect(result.total).toBe(56.86);
      expect(result.items).toHaveLength(0);
      expect(result.isPdfOnly).toBe(true);
      expect(result.requiresPdfParsing).toBe(true);
    });

    it('should detect UberEats from noreply@uber.com', () => {
      expect(detectPlatform(uberEatsPdfOnlyReceipt)).toBe('UberEats');
    });

    it('should extract restaurant from PDF-only format', () => {
      const restaurant = extractRestaurant(uberEatsPdfOnlyReceipt.body, 'UberEats');
      expect(restaurant).toBe('Walmart');
    });
  });
});
