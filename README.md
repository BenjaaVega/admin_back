# admin_back

## Requisitos Funcionales

- **RF01:** Usuario administrador dedicado para la aplicación con capacidades extendidas sobre el resto de los perfiles.
- **RF02:** Visualización de agendamientos disponibles por propiedad, permitiendo aplicar descuentos de hasta un 10% al precio cuando convenga para incentivar su compra.
- **RF03:** Los administradores pueden comprar agendamientos específicos para su grupo; un usuario normal ve un mensaje de error si intenta hacerlo.
- **RF04:** Los administradores pueden subastar los agendamientos de propiedades que hayan comprado para su grupo; los usuarios normales reciben un error si lo intentan.
- **RF05:** Los administradores pueden proponer, aceptar o rechazar intercambios en subastas de otros grupos, con mensajes de error para usuarios normales que intenten esta acción.
- **RF06:** La cantidad de agendamientos disponibles para compra se ajusta dinámicamente según si otro grupo los adquirió o si nuestro grupo los retuvo sin subastarlos.
- **RF07:** Las actualizaciones de compras se muestran en tiempo real mediante websockets para reflejar cambios al instante.
- **RF08:** El usuario administrador puede activar descuentos para los agendamientos de su grupo; cualquier usuario normal que lo intente recibe un mensaje de error.
