export const hapticLight = () => navigator?.vibrate?.(10);
export const hapticMedium = () => navigator?.vibrate?.(30);
export const hapticSuccess = () => navigator?.vibrate?.([10, 30, 10]);
export const hapticError = () => navigator?.vibrate?.([30, 50, 30]);
